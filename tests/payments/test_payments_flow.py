import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.db.models import Field, ForeignKey, OneToOneField
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import PaymentStatus

User = get_user_model()


# ----------------------------
# Helpers: users & defaults
# ----------------------------
def make_user(uid: str):
    """Create a user compatible with custom AUTH_USER_MODEL."""
    if hasattr(User, "username"):
        return User.objects.create_user(
            username=uid, email=f"{uid}@example.com", password="pass1234"
        )
    return User.objects.create_user(email=f"{uid}@example.com", password="pass1234")


def _default_for_field(f: Field):
    """Minimal default value for required primitive fields."""
    if f.has_default():
        return f.get_default()
    if getattr(f, "null", False):
        return None
    if isinstance(f, (models.CharField, models.TextField, models.SlugField)):
        return "x"
    if isinstance(f, models.EmailField):
        return "x@example.com"
    if isinstance(
        f,
        (
            models.IntegerField,
            models.BigIntegerField,
            models.SmallIntegerField,
            models.PositiveIntegerField,
        ),
    ):
        return 0
    if isinstance(f, models.BooleanField):
        return False
    if isinstance(f, models.DateTimeField):
        return timezone.now()
    if isinstance(f, models.DateField):
        return timezone.now().date()
    return "x"


# ----------------------------
# Introspection helpers
# ----------------------------
def order_user_field() -> Field | None:
    """Return the concrete user-like relation on Order."""
    candidates = ["user", "customer", "owner", "account"]
    for f in Order._meta.get_fields():
        if isinstance(f, Field) and f.name in candidates:
            return f
    return None


def order_has_field(name: str) -> bool:
    try:
        Order._meta.get_field(name)
        return True
    except Exception:
        return False


def _is_required_fk(name: str) -> bool:
    try:
        f = Order._meta.get_field(name)
        return isinstance(f, (ForeignKey, OneToOneField)) and not getattr(f, "null", False)
    except Exception:
        return False


# ----------------------------
# Builders for related objects
# ----------------------------
def _create_minimal_instance(Model, hints: dict | None = None):
    """
    Create a minimal instance of Model:
    - Use provided hints for known fields (e.g., codes, flags).
    - Fill other required primitive fields with minimal defaults.
    - Skip relational fields.
    """
    hints = hints or {}
    kwargs = dict(hints)

    for field in Model._meta.get_fields():
        if not isinstance(field, Field):
            continue
        if field.name in kwargs:
            continue
        if getattr(field, "primary_key", False) or field.auto_created:
            continue
        if isinstance(field, (ForeignKey, OneToOneField)):
            # don't cascade-create deep graphs in tests
            continue
        required = (
            not getattr(field, "null", False)
            and not getattr(field, "blank", False)
            and not field.has_default()
        )
        if required:
            kwargs[field.name] = _default_for_field(field)

    return Model.objects.create(**kwargs)


def ensure_customer_for_user(user):
    """
    Return existing Customer linked to this user if present; otherwise create one.
    Avoid UNIQUE(user_id) violations when a signal already created it.
    """
    f = Order._meta.get_field("customer")  # raises if not present
    CustomerModel = f.related_model

    user_link_field_name = None
    for candidate in ("user", "account", "owner"):
        try:
            cf = CustomerModel._meta.get_field(candidate)
            if isinstance(cf, (ForeignKey, OneToOneField)) and cf.related_model == User:
                user_link_field_name = candidate
                break
        except Exception:
            continue

    if user_link_field_name:
        try:
            return CustomerModel.objects.get(**{user_link_field_name: user})
        except CustomerModel.DoesNotExist:
            pass

    # Build minimal kwargs
    kwargs = {}
    if user_link_field_name:
        kwargs[user_link_field_name] = user

    for field in CustomerModel._meta.get_fields():
        if not isinstance(field, Field):
            continue
        if field.name in kwargs:
            continue
        if getattr(field, "primary_key", False) or field.auto_created:
            continue
        if isinstance(field, (ForeignKey, OneToOneField)):
            continue
        required = (
            not getattr(field, "null", False)
            and not getattr(field, "blank", False)
            and not field.has_default()
        )
        if required:
            kwargs[field.name] = _default_for_field(field)

    try:
        return CustomerModel.objects.create(**kwargs)
    except IntegrityError:
        if user_link_field_name:
            return CustomerModel.objects.get(**{user_link_field_name: user})
        raise


def ensure_address_for_order(field_name: str, user=None, customer=None):
    """
    If Order.<field_name> is required FK, create a minimal Address instance and return it.
    Tries to link to user/customer if such a field exists on Address model.
    """
    f = Order._meta.get_field(field_name)  # ForeignKey
    AddressModel = f.related_model

    kwargs = {}
    for name, value in (("customer", customer), ("user", user), ("owner", user), ("account", user)):
        if value is None:
            continue
        try:
            relf = AddressModel._meta.get_field(name)
            if isinstance(relf, (ForeignKey, OneToOneField)):
                kwargs[name] = value
                break
        except Exception:
            continue

    return _create_minimal_instance(AddressModel, hints=kwargs)


def ensure_shipping_method():
    """Create a minimal shipping method if Order.shipping_method is required."""
    f = Order._meta.get_field("shipping_method")  # ForeignKey
    ShipModel = f.related_model
    # try to use common hints to satisfy unique constraints
    hints = {}
    # common fields: name, code, price, is_active/enabled
    for fname in ("name",):
        if any(getattr(ff, "name", "") == fname for ff in ShipModel._meta.fields):
            hints["name"] = f"Test Shipping {int(timezone.now().timestamp())}"
            break
    for fname in ("code", "slug"):
        if any(getattr(ff, "name", "") == fname for ff in ShipModel._meta.fields):
            hints[fname] = f"TST{int(timezone.now().timestamp())}"
            break
    for fname in ("price", "cost", "base_price"):
        if any(getattr(ff, "name", "") == fname for ff in ShipModel._meta.fields):
            hints[fname] = 0
            break
    for fname in ("is_active", "enabled", "active"):
        if any(getattr(ff, "name", "") == fname for ff in ShipModel._meta.fields):
            hints[fname] = True
            break

    return _create_minimal_instance(ShipModel, hints=hints)


# ----------------------------
# Build Order kwargs robustly
# ----------------------------
def build_order_kwargs(user, number: str, payable: int | None = None) -> dict:
    kwargs = {"number": number}
    customer_obj = None

    # user/customer on Order
    uf = order_user_field()
    if uf:
        if uf.name == "customer":
            customer_obj = ensure_customer_for_user(user)
            kwargs["customer"] = customer_obj
        else:
            kwargs[uf.name] = user

    # totals if real field
    if payable is not None and order_has_field("total_payable"):
        kwargs["total_payable"] = payable

    # required addresses
    if _is_required_fk("shipping_address"):
        kwargs["shipping_address"] = ensure_address_for_order(
            "shipping_address", user=user, customer=customer_obj
        )
    if _is_required_fk("billing_address"):
        kwargs["billing_address"] = ensure_address_for_order(
            "billing_address", user=user, customer=customer_obj
        )

    # required shipping method
    if _is_required_fk("shipping_method"):
        kwargs["shipping_method"] = ensure_shipping_method()

    return kwargs


# ----------------------------
# Tests
# ----------------------------
@pytest.mark.django_db
def test_cod_checkout_flow(client):
    user = make_user("u1")
    client.force_login(user)

    order = Order.objects.create(**build_order_kwargs(user, "ORD-COD-1", payable=120000))

    # GET checkout page
    resp = client.get(reverse("payments:checkout", kwargs={"order_number": order.number}))
    assert resp.status_code == 200

    # POST COD
    resp = client.post(
        reverse("payments:checkout", kwargs={"order_number": order.number}), {"method": "cod"}
    )
    assert resp.status_code in (302, 301)

    order.refresh_from_db()
    assert bool(getattr(order, "is_paid", False)) is True
    p = order.payments.first()
    assert p is not None
    assert p.status == PaymentStatus.SUCCEEDED
    assert p.provider == "cod"


@pytest.mark.django_db
def test_fake_online_success_flow(client):
    user = make_user("u2")
    client.force_login(user)

    order = Order.objects.create(**build_order_kwargs(user, "ORD-ONLINE-1", payable=50000))

    # start online
    resp = client.post(
        reverse("payments:checkout", kwargs={"order_number": order.number}), {"method": "online"}
    )
    assert resp.status_code in (302, 301)

    # mock page
    resp2 = client.get(reverse("payments:mock_gateway", kwargs={"order_number": order.number}))
    assert resp2.status_code == 200

    # success
    resp3 = client.get(reverse("payments:success", kwargs={"order_number": order.number}))
    assert resp3.status_code in (200, 302)

    order.refresh_from_db()
    p = order.payments.first()
    assert p is not None
    assert p.status == PaymentStatus.SUCCEEDED
    assert bool(getattr(order, "is_paid", False)) is True


@pytest.mark.django_db
def test_fake_online_fail_and_retry(client):
    user = make_user("u3")
    client.force_login(user)

    order = Order.objects.create(**build_order_kwargs(user, "ORD-ONLINE-2", payable=80000))

    # first try -> online -> fail
    client.post(
        reverse("payments:checkout", kwargs={"order_number": order.number}), {"method": "online"}
    )
    client.get(reverse("payments:failed", kwargs={"order_number": order.number}))
    order.refresh_from_db()
    p1 = order.payments.first()
    assert p1 is not None
    assert p1.status == PaymentStatus.FAILED
    assert (p1.attempt_count or 0) >= 1
    assert bool(getattr(order, "is_paid", False)) is False

    # retry -> online -> success
    client.post(
        reverse("payments:checkout", kwargs={"order_number": order.number}), {"method": "online"}
    )
    client.get(reverse("payments:success", kwargs={"order_number": order.number}))
    order.refresh_from_db()
    p2 = order.payments.first()
    assert p2 is not None
    assert p2.status == PaymentStatus.SUCCEEDED
    assert bool(getattr(order, "is_paid", False)) is True
