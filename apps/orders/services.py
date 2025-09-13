# apps/orders/services.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import FieldDoesNotExist
from django.db import models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    ShippingMethod,
)

if TYPE_CHECKING:
    from apps.accounts.models import Address
    from apps.customers.models import Customer
    from apps.payments.models import Payment as PaymentModel

    # Optional: add concrete types for product & variant if you want stronger hints
    # from apps.catalog.models import Product, ProductVariant


# ----------------------------
# helpers
# ----------------------------
def _to_decimal(value, default: str = "0.00") -> Decimal:
    """Coerce arbitrary value to Decimal; fall back to given default on parse errors."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _unit_price_for(product, variant=None) -> Decimal:
    """
    Compute unit price snapshot for a product/variant.
    - If variant has explicit final_price, prefer it.
    - Else base product price + variant.extra_price (if present).
    """
    base = _to_decimal(getattr(product, "price", "0.00"))
    if variant is not None:
        if getattr(variant, "final_price", None) is not None:
            return _to_decimal(getattr(variant, "final_price"))
        extra = _to_decimal(getattr(variant, "extra_price", "0.00"))
        return base + extra
    return base


# ----------------------------
# cart APIs
# ----------------------------
@transaction.atomic
def add_to_cart(*, cart: Cart, product, variant=None, qty: int = 1) -> CartItem:
    """
    Add a product/variant to the given cart, increasing quantity when item already exists.

    Args:
        cart: Current cart instance (guest or user cart).
        product: Product to add.
        variant: Optional variant to pair with product.
        qty: Quantity to add (>=1).

    Returns:
        The affected/created CartItem (with current unit_price snapshot).
    """
    qty = int(qty or 1)
    if qty < 1:
        qty = 1

    unit_price = _unit_price_for(product, variant)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        variant=variant,
        defaults={"unit_price": unit_price, "quantity": qty},
    )
    if not created:
        # Safe, concurrent-friendly increment
        CartItem.objects.filter(pk=item.pk).update(quantity=F("quantity") + qty)
        item.refresh_from_db(fields=["quantity"])
        # Keep latest unit price snapshot policy
        if item.unit_price != unit_price:
            item.unit_price = unit_price
            item.save(update_fields=["unit_price"])
    return item


def set_shipping_method(*, cart: Cart, shipping_method: ShippingMethod | None) -> None:
    """Set shipping method on cart if the field exists."""
    if shipping_method is None:
        return
    if hasattr(cart, "shipping_method"):
        cart.shipping_method = shipping_method
        cart.save(update_fields=["shipping_method"])


def cart_total(cart: Cart) -> Decimal:
    """
    Compute cart total = sum(unit_price * quantity) + shipping_cost.
    Uses ExpressionWrapper to keep DB-side arithmetic typed as Decimal.
    """
    line_total = ExpressionWrapper(
        F("unit_price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    agg = cart.items.aggregate(total=Sum(line_total))
    items_total = _to_decimal(agg["total"] or "0.00")

    sm = getattr(cart, "shipping_method", None)
    shipping_cost = _to_decimal(getattr(sm, "base_price", "0.00")) if sm else Decimal("0.00")
    return items_total + shipping_cost


# ----------------------------
# order creation
# ----------------------------
def _assign_shipping_on_order_kwargs(
    order_kwargs: dict, shipping_method: ShippingMethod | None
) -> Decimal:
    """
    Assign into order_kwargs['shipping_method'] according to Order field type.
    If FK to ShippingMethod → assign instance; else assign shipping code string.
    Returns the base shipping cost.
    """
    if not shipping_method:
        return Decimal("0.00")

    try:
        field = Order._meta.get_field("shipping_method")
    except FieldDoesNotExist:
        return _to_decimal(getattr(shipping_method, "base_price", "0.00"))

    shipping_cost = _to_decimal(getattr(shipping_method, "base_price", "0.00"))
    if (
        isinstance(field, models.ForeignKey)
        and field.remote_field
        and field.remote_field.model == ShippingMethod
    ):
        order_kwargs["shipping_method"] = shipping_method
    else:
        order_kwargs["shipping_method"] = getattr(shipping_method, "code", "") or ""
    return shipping_cost


@transaction.atomic
def create_order_from_cart(
    *,
    customer: Customer,
    shipping_address: Address,
    cart: Cart,
    shipping_method: ShippingMethod | None = None,
    payment_method: str = PaymentMethod.GATEWAY,
    discount: Decimal = Decimal("0.00"),
    notes: str | None = None,
) -> tuple[Order, PaymentModel | None]:
    """
    Create an Order (and items) from a cart snapshot.
    Returns (order, payment) — here payment is None; payments app will create attempts later.
    """
    order_kwargs: dict = {
        "customer": customer,
        "shipping_address": shipping_address,
        "status": OrderStatus.PENDING,
        "payment_method": payment_method,
        "discount_total": _to_decimal(discount),
    }
    if notes:
        order_kwargs["notes"] = notes

    shipping_cost = _assign_shipping_on_order_kwargs(order_kwargs, shipping_method)
    order_kwargs["shipping_cost"] = shipping_cost

    order = Order.objects.create(**order_kwargs)

    # Copy items (bulk_create for performance)
    items_qs = CartItem.objects.select_related("product", "variant").filter(cart=cart)
    order_items = [
        OrderItem(
            order=order,
            product=ci.product,
            variant=ci.variant,
            product_name=getattr(ci.product, "name", "") or str(ci.product),
            sku=(getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", "")),
            unit_price=_to_decimal(ci.unit_price),
            quantity=int(ci.quantity),
        )
        for ci in items_qs
    ]
    if order_items:
        OrderItem.objects.bulk_create(order_items)

    # Totals
    if hasattr(order, "recalc_totals"):
        order.recalc_totals(save=True)
    else:
        items_total = sum(
            (oi.unit_price * oi.quantity for oi in order.items.all()),
            Decimal("0.00"),
        )
        grand = (
            items_total
            + _to_decimal(order_kwargs["shipping_cost"])
            - _to_decimal(order_kwargs["discount_total"])
        )
        if hasattr(order, "subtotal"):
            order.subtotal = items_total
        if hasattr(order, "grand_total"):
            order.grand_total = grand
        order.save()

    # Clear cart
    cart.items.all().delete()

    # payments app will handle actual Payment row
    return order, None


__all__ = [
    "add_to_cart",
    "set_shipping_method",
    "cart_total",
    "create_order_from_cart",
]
