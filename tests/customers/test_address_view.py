# tests/customers/test_address_views.py
import pytest
from django.urls import reverse
from model_bakery import baker


@pytest.mark.django_db
def test_address_create_sets_default_flags(client):
    user = baker.make("accounts.User")
    client.force_login(user)
    resp = client.post(
        reverse("customers:address_create"),
        data={
            "full_name": "John Doe",
            "phone": "+989121234567",
            "line1": "Valiasr St",
            "line2": "",
            "city": "Tehran",
            "province": "Tehran",
            "postal_code": "12345",
            "country": "IR",
            "set_as_default_shipping": True,
            "set_as_default_billing": True,
        },
    )
    assert resp.status_code == 302
    assert user.addresses.filter(default_shipping=True).count() == 1
    assert user.addresses.filter(default_billing=True).count() == 1
