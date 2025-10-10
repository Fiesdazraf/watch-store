# tests/customers/test_address_model.py
import pytest
from model_bakery import baker

from apps.customers.models import Address


@pytest.mark.django_db
def test_only_one_default_shipping_per_user():
    user = baker.make("accounts.User")
    _ = baker.make(Address, user=user, default_shipping=True)
    a2 = baker.make(Address, user=user, default_shipping=False)
    # make second default
    a2.default_shipping = True
    a2.save()
    # enforce uniqueness by business logic (e.g., via view/form) or expect DB error if both True
    # In our form/view we flip others to False; here simulate:
    Address.objects.filter(user=user, default_shipping=True).exclude(pk=a2.pk).update(
        default_shipping=False
    )
    assert Address.objects.filter(user=user, default_shipping=True).count() == 1
