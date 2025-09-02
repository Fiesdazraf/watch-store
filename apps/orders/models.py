from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, UniqueConstraint

from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Address, Customer


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

    def __str__(self):
        return f"Cart #{self.pk}"

    def get_subtotal(self) -> Decimal:
        # safe sum even if some items have null unit_price (shouldn't after this migration)
        total = Decimal("0.00")
        for item in self.items.all():
            total += item.subtotal()
        return total


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    # Snapshot of unit price at the time of adding to cart (non-null to avoid admin errors)
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

    def subtotal(self) -> Decimal:
        return (self.unit_price or Decimal("0.00")) * self.quantity

    def __str__(self):
        return f"{self.product} x{self.quantity}"


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


class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    shipping_address = models.ForeignKey(
        Address, on_delete=models.PROTECT, related_name="shipping_orders"
    )

    status = models.CharField(
        max_length=12, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.GATEWAY
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    number = models.CharField(max_length=16, unique=True, blank=True)

    class Meta:
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["placed_at"]),
        ]

    def recalc_totals(self, save: bool = True) -> Decimal:
        self.subtotal = sum((item.total_price for item in self.items.all()), Decimal("0.00"))
        self.grand_total = self.subtotal + self.shipping_cost - self.discount_total
        if save:
            self.save(update_fields=["subtotal", "grand_total", "updated_at"])
        return self.grand_total

    def save(self, *args, **kwargs):
        new = self.pk is None
        super().save(*args, **kwargs)
        if new and not self.number:
            self.number = f"SW{self.id:08d}"  # e.g., SW00000042
            super().save(update_fields=["number"])

    def __str__(self):
        return f"Order {self.number or self.id} - {self.get_status_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)

    # Snapshots for denormalization (safe against later changes)
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=40, blank=True)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=["sku"])]
        constraints = [
            models.CheckConstraint(check=Q(quantity__gt=0), name="orderitem_quantity_gt_0"),
        ]

    @property
    def total_price(self) -> Decimal:
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


# Optional: keep this here for now (better as a service in apps/orders/services.py)
def add_to_cart(cart: Cart, product: Product, variant: ProductVariant | None = None, qty: int = 1):
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
        # keep snapshot consistent with current price
        item.unit_price = unit_price
        item.save(update_fields=["quantity", "unit_price"])
    return item
