# apps/orders/services.py
from decimal import Decimal

from django.db import transaction

from .models import CartItem, Order, OrderItem


@transaction.atomic
def create_order_from_cart(customer, shipping_address, cart) -> Order:
    order = Order.objects.create(
        customer=customer,
        shipping_address=shipping_address,
        status="pending",
        payment_method="gateway",
        subtotal=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
        discount_total=Decimal("0.00"),
        grand_total=Decimal("0.00"),
    )
    subtotal = Decimal("0.00")
    for ci in CartItem.objects.select_related("product", "variant").filter(cart=cart):
        name = ci.product.title
        sku = getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", "")
        unit_price = ci.unit_price
        qty = ci.quantity

        OrderItem.objects.create(
            order=order,
            product=ci.product,
            variant=ci.variant,
            product_name=name,
            sku=sku,
            unit_price=unit_price,
            quantity=qty,
        )
        subtotal += unit_price * qty

    order.subtotal = subtotal
    order.grand_total = subtotal + order.shipping_cost - order.discount_total
    order.save(update_fields=["subtotal", "grand_total"])

    # پاک کردن cart
    cart.items.all().delete()
    return order
