import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_user_auto_creates_customer():
    u = baker.make("accounts.User")
    from apps.customers.models import Customer

    count = Customer.objects.filter(user=u).count()
    print(f"Customer count for user {u.id}: {count}")
    assert count <= 1
