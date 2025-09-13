# tests/conftest.py
import shutil
import tempfile
from decimal import Decimal

import pytest
from django.test.utils import override_settings
from model_bakery import baker

from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, OrderStatus, PaymentMethod
from apps.payments.models import Payment


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


# tests/conftest.py
@pytest.fixture
def order_factory(db, customer, address, shipping_method, product, variant):
    """
    make_order(
        user=None,
        status=...,
        payment_status=None,
        payment_method=...,
        qty=1,
        with_variant=True,
    )
    - اگر user پاس داده شود، customer براساس همان user ساخته/گرفته می‌شود.
    - اگر payment_status پاس داده شود، Payment مرتبط هم ساخته می‌شود.
    """

    def make_order(
        *,
        user=None,
        status=OrderStatus.PENDING,
        payment_status=None,
        payment_method=PaymentMethod.GATEWAY,
        qty=1,
        with_variant=True,
    ):
        # resolve customer
        if user is not None:
            cust, _ = Customer.objects.get_or_create(user=user)
        else:
            cust = customer

        # normalize status
        if isinstance(status, str):
            status = OrderStatus(status)

        order = Order.objects.create(
            customer=cust,
            shipping_address=address,
            shipping_method=shipping_method,
            status=status,
            payment_method=payment_method,
        )

        unit_price = getattr(product, "price", Decimal("0.00")) or Decimal("0.00")
        if with_variant and variant:
            unit_price += getattr(variant, "extra_price", Decimal("0.00")) or Decimal("0.00")

        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant if with_variant else None,
            unit_price=unit_price,
            quantity=qty,
            product_name=getattr(product, "title", getattr(product, "name", str(product))),
            sku=(getattr(variant, "sku", "") if with_variant else getattr(product, "sku", "")),
        )

        # محاسبه مجموع تا مبلغ پرداخت درست شود
        order.recalc_totals(save=True)

        # اگر تست payment_status خواست، Payment بساز
        if payment_status is not None:
            # فقط فیلدهایی را پاس بده که واقعا در مدل Payment وجود دارند
            field_names = {
                f.name for f in Payment._meta.get_fields() if getattr(f, "concrete", False)
            }
            candidate = {
                "order": order,  # حتما وجود دارد (FK یا O2O)
                "amount": order.grand_total,  # اگر در مدل amount نداشته باشید، فیلتر می‌شود
                "status": payment_status,  # مثلا "paid", "failed"
                "method": payment_method,  # اگر method ندارید، حذف می‌شود
                "transaction_id": "TST-12345",  # اگر ندارید، حذف می‌شود
            }
            data = {k: v for k, v in candidate.items() if k in field_names}
            Payment.objects.create(**data)

        return order

    return make_order


@pytest.fixture
def user_factory(db, django_user_model):
    def make_user(email="u@example.com", password="x", **extra):
        return django_user_model.objects.create_user(email=email, password=password, **extra)

    return make_user
