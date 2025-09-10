import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_cart_page_renders(client, cart):
    # Usually "orders:cart_detail" or similar
    url = reverse("orders:cart_detail")
    # optionally login if required
    client.force_login(cart.user)
    resp = client.get(url)
    assert resp.status_code == 200
    assert "cart" in resp.context


def test_add_to_cart_view(client, user, product, variant):
    client.force_login(user)
    url = reverse("orders:add_to_cart", args=[product.id])
    resp = client.post(url, {"qty": 2, "variant_id": variant.id})
    assert resp.status_code in (302, 303)  # redirect back to cart or product page


def test_remove_cart_item_view(client, cart, product, variant):
    client.force_login(cart.user)
    from apps.orders import services

    item = services.add_to_cart(cart=cart, product=product, variant=variant, qty=1)
    url = reverse("orders:remove_from_cart", args=[item.id])
    resp = client.post(url)
    assert resp.status_code in (302, 303)
