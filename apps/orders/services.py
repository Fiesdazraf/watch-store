from decimal import Decimal

from django.db import transaction

from apps.accounts.models import Address
from apps.customers.models import Customer
from apps.orders.models import ShippingMethod

from .models import Cart, CartItem, Order, OrderItem, OrderStatus, Payment, PaymentMethod


@transaction.atomic
def create_order_from_cart(
    *,
    customer: Customer,
    shipping_address: Address,
    cart: Cart,
    shipping_method: ShippingMethod | None = None,
    payment_method: str = PaymentMethod.GATEWAY,
    discount: Decimal = Decimal("0.00"),
) -> tuple[Order, Payment | None]:
    """
    Create an Order from a Cart, snapshotting prices and items.
    Returns (Order, Payment or None).
    """
    if cart.items.count() == 0:
        raise ValueError("Cart is empty.")

    shipping_cost = shipping_method.base_price if shipping_method is not None else Decimal("0.00")

    order = Order.objects.create(
        customer=customer,
        shipping_address=shipping_address,
        shipping_method=shipping_method,
        status=(
            OrderStatus.PENDING if payment_method == PaymentMethod.COD else OrderStatus.PENDING
        ),  # later updated to PAID
        payment_method=payment_method,
        shipping_cost=shipping_cost,
        discount_total=discount,
    )

    # Copy items from cart
    for ci in CartItem.objects.select_related("product", "variant").filter(cart=cart):
        OrderItem.objects.create(
            order=order,
            product=ci.product,
            variant=ci.variant,
            product_name=getattr(ci.product, "name", "") or str(ci.product),
            sku=getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", ""),
            unit_price=ci.unit_price,
            quantity=ci.quantity,
        )

    # Calculate totals with order method
    order.recalc_totals(save=True)

    # Create Payment row if needed
    payment = None
    if payment_method in {PaymentMethod.GATEWAY, PaymentMethod.CARD, PaymentMethod.FAKE}:
        payment = Payment.objects.create(
            order=order,
            amount=order.grand_total,
            method=payment_method,
            status=Payment.Status.INITIATED,
        )

    # Clear cart items
    cart.items.all().delete()

    return order, payment
