# apps/orders/models.py
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, QuerySet, UniqueConstraint
from django.urls import reverse

from apps.accounts.models import Address
from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer

if TYPE_CHECKING:
    pass


# =============================================================================
# Cart / CartItem
# =============================================================================
class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        null=True,
        blank=True,
    )
    # For anonymous carts (session-based)
    session_key = models.CharField(max_length=40, blank=True)
    shipping_method = models.ForeignKey(
        "orders.ShippingMethod",
        on_delete=models.SET_NULL,
        related_name="carts",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Ensure at least one of user or session_key is present
            models.CheckConstraint(
                check=Q(user__isnull=False) | ~Q(session_key=""),
                name="cart_user_or_session_required",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Cart #{self.pk}"

    def get_subtotal(self) -> Decimal:
        total = Decimal("0.00")
        for unit_price, qty in self.items.values_list("unit_price", "quantity"):
            total += (unit_price or Decimal("0.00")) * qty
        return total

    @property
    def total_amount(self) -> Decimal:
        """
        Sum of cart items + shipping cost (if any).
        Uses services.cart_total to stay in sync with business logic.
        """
        from .services import cart_total  # local import to avoid circulars

        return cart_total(self)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    # Snapshot of unit price at the time of adding to cart
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            # one row per (cart, product) when variant IS NULL
            UniqueConstraint(
                fields=["cart", "product"],
                condition=Q(variant__isnull=True),
                name="uniq_cart_product_no_variant",
            ),
            # one row per (cart, product, variant) when variant IS NOT NULL
            UniqueConstraint(
                fields=["cart", "product", "variant"],
                condition=Q(variant__isnull=False),
                name="uniq_cart_product_with_variant",
            ),
            # quantity must be > 0
            models.CheckConstraint(check=Q(quantity__gt=0), name="cartitem_quantity_gt_0"),
        ]
        indexes = [models.Index(fields=["cart"])]

    def subtotal(self) -> Decimal:
        return (self.unit_price or Decimal("0.00")) * self.quantity

    def __str__(self) -> str:
        return f"{self.product} x{self.quantity}"


# =============================================================================
# ShippingMethod
# =============================================================================
class ShippingMethod(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=60, unique=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    est_days_min = models.PositiveSmallIntegerField(default=2)
    est_days_max = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Coerce in-memory value to Decimal if factory/fixture sets a str
        if isinstance(getattr(self, "base_price", None), str):
            try:
                self.base_price = Decimal(self.base_price)
            except Exception:
                pass

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.base_price})"


# =============================================================================
# Order / OrderItem
# =============================================================================
class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    SHIPPED = "shipped", "Shipped"
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class OrderStatusLog(models.Model):
    order = models.ForeignKey("Order", related_name="status_logs", on_delete=models.CASCADE)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
    )
    from_status = models.CharField(max_length=32)
    to_status = models.CharField(max_length=32)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order#{self.order_id}: {self.from_status} → {self.to_status}"


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on Delivery"
    CARD = "card", "Credit/Debit Card"
    GATEWAY = "gateway", "Online Gateway"
    FAKE = "fake", "Fake (Demo)"


class UserAwareOrderQuerySet(QuerySet):
    """Allow filtering with 'user' as an alias for 'customer__user'."""

    @staticmethod
    def _rewrite_user_kwargs(kwargs: dict) -> dict:
        if not kwargs:
            return kwargs
        rewritten = {}
        for key, val in kwargs.items():
            if key == "user":
                rewritten["customer__user"] = val
            elif key.startswith("user__"):
                # e.g. user__email -> customer__user__email
                rewritten["customer__" + key] = val
            else:
                rewritten[key] = val
        return rewritten

    def filter(self, *args, **kwargs):
        return super().filter(*args, **self._rewrite_user_kwargs(kwargs))

    def exclude(self, *args, **kwargs):
        return super().exclude(*args, **self._rewrite_user_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*args, **self._rewrite_user_kwargs(kwargs))


class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    shipping_address = models.ForeignKey(
        Address, on_delete=models.PROTECT, related_name="shipping_orders"
    )
    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=12, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.GATEWAY
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    number = models.CharField(max_length=16, unique=True, blank=True)

    # Manager that understands `user=` (aliases to customer__user)
    objects = UserAwareOrderQuerySet.as_manager()

    class Meta:
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["placed_at"]),
            models.Index(fields=["number"]),
        ]

    # ---------- Payment-facing helpers ----------
    @property
    def total_payable(self) -> Decimal:
        return self.grand_total

    @property
    def total_amount(self) -> Decimal:
        """
        Backwards-compat shim for tests expecting `order.total_amount`.
        Returns the final amount payable (grand_total). Recomputes if needed.
        """
        if not self.grand_total or self.grand_total <= Decimal("0.00"):
            try:
                self.recalc_totals(save=False)
            except Exception:
                pass
        return self.grand_total or Decimal("0.00")

    @property
    def payment_obj(self):
        return getattr(self, "payment", None)

    @property
    def payment_status(self) -> str:
        p = self.payment_obj
        return getattr(p, "status", "none")

    @property
    def is_paid(self) -> bool:
        if getattr(self, "payment", None) and getattr(self.payment, "status", None) == "paid":
            return True
        return self.status == OrderStatus.PAID

    @property
    def is_awaiting_payment(self) -> bool:
        return self.status == OrderStatus.PENDING

    def get_checkout_payment_url(self) -> str:
        return reverse("payments:checkout_payment", kwargs={"order_number": self.number})

    def get_payment_success_url(self) -> str:
        return reverse("payments:success", kwargs={"order_number": self.number})

    def get_payment_failed_url(self) -> str:
        return reverse("payments:failed", kwargs={"order_number": self.number})

    def get_retry_payment_url(self) -> str:
        return self.get_checkout_payment_url()

    def get_absolute_url(self) -> str:
        return reverse("orders:detail", kwargs={"number": self.number})

    # -------------------------
    # Calculations / helpers
    # -------------------------

    def recalc_totals(self, save: bool = True) -> Decimal:
        subtotal = Decimal("0.00")
        for unit_price, qty in self.items.values_list("unit_price", "quantity"):
            subtotal += (unit_price or Decimal("0.00")) * qty

        def _q2(x: Decimal) -> Decimal:
            return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        self.subtotal = _q2(subtotal)
        total = (
            self.subtotal
            + (self.shipping_cost or Decimal("0.00"))
            - (self.discount_total or Decimal("0.00"))
        )
        total = _q2(total)
        self.grand_total = total if total >= Decimal("0.00") else Decimal("0.00")

        if save:
            self.save(update_fields=["subtotal", "grand_total", "updated_at"])
        return self.grand_total

    def save(self, *args, **kwargs):
        new = self.pk is None
        super().save(*args, **kwargs)
        if new and not self.number:
            self.number = f"SW{self.id:08d}"
            super().save(update_fields=["number"])

    def __str__(self) -> str:
        return f"Order {self.number or self.id} - {self.get_status_display()}"

    def set_status(self, new_status: str, by_user=None, note: str | None = None):
        """
        Safe status transition using OrderStatus.
        Allowed:
          pending -> paid | canceled
          paid    -> shipped | canceled
          shipped -> completed
          completed (terminal)
          canceled (terminal)
        """
        from django.core.exceptions import ValidationError

        allowed = {
            OrderStatus.PENDING: {OrderStatus.PROCESSING, OrderStatus.PAID, OrderStatus.CANCELED},
            OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELED},
            OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELED},
            OrderStatus.SHIPPED: {OrderStatus.COMPLETED},
            OrderStatus.COMPLETED: set(),
            OrderStatus.CANCELED: set(),
        }

        if new_status not in OrderStatus.values:
            raise ValidationError("Invalid status")

        if new_status not in allowed.get(self.status, set()):
            raise ValidationError(f"Illegal transition from {self.status} to {new_status}")

        with transaction.atomic():
            self.status
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])
            # اگر بعداً StatusLog اضافه کردی، اینجا ثبتش کن:
            # self.status_logs.create(old_status=old, new_status=new_status, by=by_user, note=note)

        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)

    product_name = models.CharField(max_length=200, blank=True)
    sku = models.CharField(max_length=64, blank=True)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=["sku"])]
        constraints = [
            models.CheckConstraint(check=Q(quantity__gt=0), name="orderitem_quantity_gt_0"),
        ]

    @property
    def total_price(self) -> Decimal:
        return (self.unit_price or Decimal("0.00")) * self.quantity

    def save(self, *args, **kwargs):
        # Use title if your Product model uses 'title'
        if not self.product_name:
            self.product_name = (
                getattr(self.product, "title", None)
                or getattr(self.product, "name", "")
                or str(self.product)
            )
        if not self.sku:
            self.sku = getattr(self.variant, "sku", "") or getattr(self.product, "sku", "") or ""
        if not self.unit_price:
            base = getattr(self.product, "price", None) or Decimal("0.00")
            extra = (
                getattr(self.variant, "extra_price", Decimal("0.00"))
                if self.variant
                else Decimal("0.00")
            )
            self.unit_price = base + extra
        super().save(*args, **kwargs)
