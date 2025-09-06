# apps/orders/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, UniqueConstraint
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Address
from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer


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
        """
        Sum using the DB to avoid Python-side loops / N+1 issues.
        """
        total = Decimal("0.00")
        for unit_price, qty in self.items.values_list("unit_price", "quantity"):
            total += (unit_price or Decimal("0.00")) * qty
        return total


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
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    est_days_min = models.PositiveSmallIntegerField(default=2)
    est_days_max = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.base_price})"


# =============================================================================
# Order / OrderItem
# =============================================================================
class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    SHIPPED = "shipped", "Shipped"
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on Delivery"
    CARD = "card", "Credit/Debit Card"
    GATEWAY = "gateway", "Online Gateway"
    # Optional demo method for portfolio
    FAKE = "fake", "Fake (Demo)"


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
    number = models.CharField(max_length=16, unique=True, blank=True)  # e.g. SW00000042

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
    def payment_obj(self):
        return getattr(self, "payment", None)

    @property
    def payment_status(self) -> str:
        p = self.payment_obj
        return getattr(p, "status", "none")

    @property
    def is_paid(self) -> bool:
        """True if either Payment says paid or OrderStatus is PAID."""
        if getattr(self, "payment", None):
            if getattr(self.payment, "status", None) == "paid":
                return True
        try:
            return self.status == OrderStatus.PAID
        except Exception:
            return False

    @property
    def is_awaiting_payment(self) -> bool:
        try:
            return self.status == self.Status.AWAITING_PAYMENT
        except AttributeError:
            return self.status.lower() in {"pending", "awaiting_payment"}

    def get_checkout_payment_url(self) -> str:
        return reverse("payments:checkout_payment", kwargs={"order_number": self.number})

    def get_payment_success_url(self) -> str:
        return reverse("payments:success", kwargs={"order_number": self.number})

    def get_payment_failed_url(self) -> str:
        return reverse("payments:failed", kwargs={"order_number": self.number})

    def get_retry_payment_url(self) -> str:
        return self.get_checkout_payment_url()

    def ensure_payment(self, default_method=None):
        from apps.payments.models import Payment

        payment, created = Payment.objects.get_or_create(
            order=self,
            defaults={
                "method": default_method if default_method is not None else None,
                "amount": self.total_payable,
                "status": "pending",
            },
        )
        if not created and payment.amount != self.total_payable:
            payment.amount = self.total_payable
            payment.save(update_fields=["amount"])
        return payment

    # -------------------------
    # Calculations / helpers
    # -------------------------
    def recalc_totals(self, save: bool = True) -> Decimal:
        subtotal = Decimal("0.00")
        for unit_price, qty in self.items.values_list("unit_price", "quantity"):
            subtotal += (unit_price or Decimal("0.00")) * qty

        self.subtotal = subtotal
        self.grand_total = (
            self.subtotal
            + (self.shipping_cost or Decimal("0.00"))
            - (self.discount_total or Decimal("0.00"))
        )

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

    # -------------------------
    # Factory from Cart
    # -------------------------
    @classmethod
    @transaction.atomic
    def create_from_cart(
        cls,
        *,
        cart: Cart,
        customer: Customer,
        address: Address,
        payment_method: str,
        shipping_method: ShippingMethod | None = None,
        discount: Decimal = Decimal("0.00"),
        tax: Decimal = Decimal("0.00"),  # not used in totals unless خودت اضافه کنی
    ) -> tuple[Order, Payment | None]:
        """
        Create an Order from a Cart:
        - Copies CartItems -> OrderItems with price snapshots
        - Snapshots shipping cost from ShippingMethod (if any)
        - Creates a Payment row when needed
        - Clears the cart on success
        """
        if cart.items.count() == 0:
            raise ValueError("Cart is empty.")

        shipping_cost = (
            shipping_method.base_price if shipping_method is not None else Decimal("0.00")
        )

        order = cls.objects.create(
            customer=customer,
            shipping_address=address,
            shipping_method=shipping_method,
            payment_method=payment_method,
            shipping_cost=shipping_cost,
            discount_total=discount,
            status=(
                OrderStatus.PENDING if payment_method == PaymentMethod.COD else OrderStatus.PENDING
            ),  # will be updated when payment succeeds
        )

        # Copy items
        for ci in cart.items.select_related("product", "variant"):
            OrderItem.objects.create(
                order=order,
                product=ci.product,
                variant=ci.variant,
                product_name=getattr(ci.product, "name", "") or str(ci.product),
                sku=(getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", "")),
                unit_price=ci.unit_price,
                quantity=ci.quantity,
            )

        # Totals
        order.recalc_totals(save=True)

        # Create payment row for non-COD (or for FAKE/GATEWAY flows)
        payment: Payment | None = None
        if payment_method in {PaymentMethod.CARD, PaymentMethod.GATEWAY, PaymentMethod.FAKE}:
            payment = Payment.objects.create(
                order=order,
                amount=order.grand_total,
                method=payment_method,
                status=Payment.Status.INITIATED,
            )

        # Clear cart
        cart.items.all().delete()

        return order, payment


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)

    # Snapshots for denormalization (safe against later changes)
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
        """
        Ensure snapshot fields are populated if admin/user forgot to set them.
        """
        if not self.product_name:
            self.product_name = getattr(self.product, "name", "") or str(self.product)

        if not self.sku:
            self.sku = getattr(self.variant, "sku", "") or getattr(self.product, "sku", "") or ""

        if not self.unit_price:
            base = getattr(self.product, "price", None)
            if base is None:
                base = Decimal("0.00")
            extra = (
                getattr(self.variant, "extra_price", Decimal("0.00"))
                if self.variant
                else Decimal("0.00")
            )
            self.unit_price = base + extra

        super().save(*args, **kwargs)


# =============================================================================
# Payment
# =============================================================================
class Payment(models.Model):
    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="IRR")
    method = models.CharField(
        max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.GATEWAY
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.INITIATED)

    # Gateway fields (generic)
    gateway_ref = models.CharField(max_length=100, blank=True)  # e.g., authority code
    transaction_id = models.CharField(max_length=100, blank=True)  # e.g., ref id / charge id
    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payment for Order {self.order.number or self.order_id} - {self.status}"

    # -------------------------
    # State transitions
    # -------------------------
    def mark_success(self, *, transaction_id: str | None = None, meta: dict | None = None) -> None:
        self.status = self.Status.SUCCESS
        if transaction_id:
            self.transaction_id = transaction_id
        if meta:
            self.raw_response.update(meta)
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "transaction_id", "raw_response", "paid_at"])

        # Update order status
        self.order.status = OrderStatus.PAID
        self.order.save(update_fields=["status", "updated_at"])

    def mark_failed(self, *, meta: dict | None = None) -> None:
        self.status = self.Status.FAILED
        if meta:
            self.raw_response.update(meta)
        self.save(update_fields=["status", "raw_response"])


# =============================================================================
# Services (helpers)
# =============================================================================
def add_to_cart(
    cart: Cart,
    product: Product,
    variant: ProductVariant | None = None,
    qty: int = 1,
) -> CartItem:
    """
    Add or increment a cart item, snapshotting the unit price at the time of add.
    """
    base = product.price
    extra = getattr(variant, "extra_price", Decimal("0.00")) if variant else Decimal("0.00")
    unit_price = base + extra

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        variant=variant,
        defaults={"unit_price": unit_price, "quantity": qty},
    )
    if not created:
        item.quantity += qty
        item.unit_price = unit_price  # keep snapshot consistent with current price
        item.save(update_fields=["quantity", "unit_price"])
    return item


@transaction.atomic
def place_order_from_cart(
    *,
    cart: Cart,
    customer: Customer,
    address: Address,
    payment_method: str,
    shipping_method: ShippingMethod | None = None,
    discount: Decimal = Decimal("0.00"),
) -> tuple[Order, Payment | None]:
    """
    High-level service to place an order:
    - Builds Order from Cart
    - Creates Payment row if needed
    - Clears Cart
    """
    order, payment = Order.create_from_cart(
        cart=cart,
        customer=customer,
        address=address,
        payment_method=payment_method,
        shipping_method=shipping_method,
        discount=discount,
    )
    return order, payment
