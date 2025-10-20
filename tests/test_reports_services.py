from datetime import datetime as pydt
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import models as djm
from django.utils import timezone

from apps.orders.models import Order, OrderStatus
from apps.orders.services import (
    get_orders_counters,
    get_sales_kpis,
    get_sales_timeseries_by_day,
)


def _build_instance_kwargs(model, owner_user=None, owner_customer=None):
    """
    Build minimal valid kwargs for address-like models.
    Fills required non-null fields dynamically.
    """
    kwargs = {}
    for f in model._meta.get_fields():
        if not isinstance(f, djm.Field) or f.auto_created:
            continue
        if f.name == "id":
            continue
        if getattr(f, "null", False) or f.has_default():
            continue
        if f.is_relation:
            if f.name == "user" and owner_user:
                kwargs[f.name] = owner_user
            elif f.name == "customer" and owner_customer:
                kwargs[f.name] = owner_customer
            continue
        if isinstance(f, (djm.CharField, djm.TextField)):
            kwargs[f.name] = "test"
        elif isinstance(f, djm.BooleanField):
            kwargs[f.name] = False
        elif isinstance(f, djm.IntegerField):
            kwargs[f.name] = 0
        elif isinstance(f, djm.DecimalField):
            kwargs[f.name] = Decimal("0")
        elif isinstance(f, djm.DateTimeField):
            kwargs[f.name] = timezone.now()
        else:
            kwargs[f.name] = "x"
    return kwargs


@pytest.mark.django_db
def test_sales_kpis_and_counters(django_user_model):
    user = django_user_model.objects.create_user(email="u@test.com", password="x")
    from apps.customers.models import Customer

    customer, _ = Customer.objects.get_or_create(user=user)

    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=user, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)

    now = timezone.now()

    # create multiple orders
    for status, total, delta in [
        (OrderStatus.PAID, 100, 1),
        (OrderStatus.PAID, 200, 2),
        ("cancelled", 300, 1),  # ← ثابت با خروجی counters
        (OrderStatus.PENDING, 50, 3),
    ]:
        Order.objects.create(
            customer=customer,
            **{shipping_field.attname: shipping_address.pk},
            status=status,
            placed_at=now - timedelta(days=delta),
            grand_total=Decimal(str(total)),
            payment_method="gateway",
            discount_total=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
        )

    kpis = get_sales_kpis()
    assert kpis["today"] >= 0
    assert kpis["week"] >= 0
    assert kpis["month"] >= 0

    counters = get_orders_counters()
    assert counters.get("paid", 0) >= 2
    assert counters.get("cancelled", 0) >= 1
    assert counters.get("pending", 0) >= 1


@pytest.mark.django_db
def test_timeseries_daily_fill_zeros(django_user_model):
    user = django_user_model.objects.create_user(email="t@test.com", password="x")
    from apps.customers.models import Customer

    customer, _ = Customer.objects.get_or_create(user=user)

    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=user, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)

    today = timezone.localdate()
    mid = today - timedelta(days=1)
    start = today - timedelta(days=2)
    end = today

    mid_dt = timezone.make_aware(pydt.combine(mid, pydt.min.time()))
    Order.objects.create(
        customer=customer,
        **{shipping_field.attname: shipping_address.pk},
        status=OrderStatus.PAID,
        placed_at=mid_dt,
        grand_total=Decimal("120.00"),
        payment_method="gateway",
        discount_total=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
    )

    series = get_sales_timeseries_by_day(start, end)
    values = [p["value"] for p in series]
    assert len(series) == 3
    assert all(isinstance(v, (int, float)) for v in values)
