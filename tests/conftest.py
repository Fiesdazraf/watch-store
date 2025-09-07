import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="u@test.com", password="pw12345", first_name="U")


@pytest.fixture
def customer(db, user):
    return baker.make("customers.Customer", user=user)


@pytest.fixture
def address(db, customer):
    return baker.make("accounts.Address", user=customer.user)


@pytest.fixture
def product(db):
    return baker.make("catalog.Product", price="100.00", is_active=True, name="P1")


@pytest.fixture
def variant(db, product):
    return baker.make(
        "catalog.ProductVariant", product=product, extra_price="20.00", is_active=True
    )


@pytest.fixture
def shipping_method(db):
    return baker.make(
        "orders.ShippingMethod", name="Post", code="post", base_price="10.00", is_active=True
    )


@pytest.fixture
def cart(db, user):
    # anonymous or user cart; here we tie to user for simplicity
    from apps.orders.models import Cart

    c = baker.make(Cart, user=user, session_key="")
    return c
