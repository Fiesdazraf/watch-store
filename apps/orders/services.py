from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from apps.accounts.models import Address
from apps.customers.models import Customer

from .models import Cart, CartItem, Order, OrderItem, OrderStatus, PaymentMethod, ShippingMethod

if TYPE_CHECKING:
    from apps.payments.models import Payment as PaymentModel


@transaction.atomic
def create_order_from_cart(
    *,
    customer: Customer,
    shipping_address: Address,
    cart: Cart,
    shipping_method: ShippingMethod | None = None,
    payment_method: str = PaymentMethod.GATEWAY,
    discount: Decimal = Decimal("0.00"),
) -> tuple[Order, PaymentModel | None]:
    if cart.items.count() == 0:
        raise ValueError("Cart is empty.")

    shipping_cost = shipping_method.base_price if shipping_method is not None else Decimal("0.00")

    order = Order.objects.create(
        customer=customer,
        shipping_address=shipping_address,
        shipping_method=shipping_method,
        status=OrderStatus.PENDING,
        payment_method=payment_method,
        shipping_cost=shipping_cost,
        discount_total=discount,
    )

    for ci in CartItem.objects.select_related("product", "variant").filter(cart=cart):
        OrderItem.objects.create(
            order=order,
            product=ci.product,
            variant=ci.variant,
            product_name=getattr(ci.product, "name", "") or str(ci.product),
            sku=(getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", "")),
            unit_price=ci.unit_price,
            quantity=ci.quantity,
        )

    order.recalc_totals(save=True)
    cart.items.all().delete()
    return order, None
