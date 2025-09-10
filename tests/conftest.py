# tests/conftest.py
import shutil
import tempfile

import pytest
from django.test.utils import override_settings
from model_bakery import baker


# ---------- Global fast test tweaks ----------
@pytest.fixture(autouse=True)
def _fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    return settings


@pytest.fixture(autouse=True)
def _email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return settings


@pytest.fixture(autouse=True)
def _dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
    return settings


@pytest.fixture(autouse=True)
def _tmp_media(settings):
    tmp_dir = tempfile.mkdtemp()
    with override_settings(MEDIA_ROOT=tmp_dir):
        yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------- Factories / Fixtures ----------
@pytest.fixture
def user(db, django_user_model):
    # مدل User شما فیلد first_name ندارد؛ فقط ایمیل و پسورد بده
    return django_user_model.objects.create_user(
        email="u@test.com",
        password="pw12345",
    )


@pytest.fixture
def customer(db, user):
    from apps.customers.models import Customer

    obj, _ = Customer.objects.get_or_create(user=user)
    return obj


@pytest.fixture
def address(db, customer):
    # Address در apps.accounts است (نه customers)
    return baker.make("accounts.Address", user=customer.user)


@pytest.fixture
def product(db):
    # به Product فیلد name نده چون در مدل شما وجود ندارد.
    # اگر price هم متفاوت بود، bakery خودش مقدار دیفالت می‌سازد.
    return baker.make("catalog.Product", is_active=True)


@pytest.fixture
def variant(db, product):
    return baker.make(
        "catalog.ProductVariant",
        product=product,
        is_active=True,
    )


@pytest.fixture
def shipping_method(db):
    return baker.make(
        "orders.ShippingMethod",
        name="Post",
        code="post",
        base_price="10.00",
        is_active=True,
    )


@pytest.fixture
def cart(db, user):
    from apps.orders.models import Cart

    return baker.make(Cart, user=user, session_key="")
