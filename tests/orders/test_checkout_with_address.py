import pytest

pytestmark = pytest.mark.django_db


def test_checkout_flow_creates_order_with_default_address(client, django_user_model):
    from django.urls import reverse
    from model_bakery import baker

    from apps.customers.models import Customer

    user = baker.make(django_user_model)
    customer = baker.make(Customer, user=user)
    client.force_login(user)

    addr = baker.make("customers.Address", user=user, default_shipping=True)
    product = baker.make("catalog.Product", price=100)

    session = client.session
    session["cart"] = {str(product.id): {"quantity": 1}}
    session.save()

    order = baker.make("orders.Order", customer=customer, shipping_address=addr)

    response = client.post(reverse("payments:checkout", args=[order.number]))
    assert response.status_code in (200, 302)
    assert customer.orders.exists()
    saved_order = customer.orders.first()
    assert saved_order.shipping_address == addr
