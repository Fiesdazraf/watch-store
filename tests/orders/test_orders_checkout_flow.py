import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_checkout_flow_creates_order_and_redirects_to_payment(
    client, user, address, product, variant, shipping_method
):
    client.force_login(user)

    # 1) add item to cart
    add_url = reverse("orders:add_to_cart", args=[product.id])
    client.post(add_url, {"qty": 1, "variant_id": variant.id})

    # 2) checkout (POST with required fields)
    checkout_url = reverse("orders:checkout")
    resp = client.post(
        checkout_url,
        {
            "address": address.id,
            "shipping_method": shipping_method.id,
            "payment_method": "fake",
            "notes": "test order",
        },
        follow=False,
    )
    assert resp.status_code in (302, 303)
    assert "payments/checkout" in resp["Location"]

    # 3) order باید ساخته شده باشد
    from apps.orders.models import Order

    order = Order.objects.filter(user=user).order_by("-id").first()
    assert order is not None
    assert float(order.total_amount) > 0
