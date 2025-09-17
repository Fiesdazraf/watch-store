from __future__ import annotations

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import models as djm
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order, OrderStatus

# ---------- Helpers ----------


def _build_instance_kwargs(model, owner_user=None, owner_customer=None) -> dict[str, Any]:
    """
    Fill minimal NOT NULL fields for address-like models, without hard assumptions.
    Works for typical Address models referenced from Order.shipping_address.
    """
    kwargs: dict[str, Any] = {}
    for f in model._meta.get_fields():
        if not isinstance(f, djm.Field) or f.auto_created:
            continue
        if f.name == "id":
            continue
        if getattr(f, "null", False) or f.has_default():
            continue
        if f.is_relation:
            if f.name == "user" and owner_user is not None:
                kwargs[f.name] = owner_user
            elif f.name == "customer" and owner_customer is not None:
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


def _make_staff_user(client, django_user_model, email="staff@test.com"):
    user = django_user_model.objects.create_user(
        **{
            getattr(django_user_model, "USERNAME_FIELD", "email"): email,
            "password": "pass",
            "is_staff": True,
        }
    )
    client.force_login(user)
    return user


def _ensure_customer_and_shipping(user):
    """
    Ensure required related instances to create an Order:
      - Customer linked to user
      - A shipping_address instance for Order.shipping_address FK
    Returns: (customer, shipping_address, shipping_attname)
    """
    customer, _ = Customer.objects.get_or_create(user=user)

    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=user, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)
    return customer, shipping_address, shipping_field.attname


# ---------- Tests: permissions & schema ----------


@pytest.mark.django_db
def test_sales_api_requires_auth_and_staff(client):
    url = reverse("backoffice:sales_api")
    # anonymous
    resp = client.get(url)
    assert resp.status_code in (302, 403)

    # non-staff user
    from django.contrib.auth import get_user_model

    User = get_user_model()
    u = User.objects.create_user(
        **{getattr(User, "USERNAME_FIELD", "email"): "user@test.com"},
        password="x",
        is_staff=False,
    )
    client.force_login(u)
    resp = client.get(url)
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_sales_api_returns_labels_and_datasets(client, django_user_model):
    staff = _make_staff_user(client, django_user_model)
    customer, shipping_address, shipping_attname = _ensure_customer_and_shipping(staff)

    # Create 3 paid orders in the last 3 days with grand_total > 0
    now = timezone.now()
    amounts = [Decimal("100.00"), Decimal("200.00"), Decimal("300.00")]
    for i, amount in enumerate(amounts):
        Order.objects.create(
            customer=customer,
            **{shipping_attname: shipping_address.pk},  # FK via attname
            status=OrderStatus.PAID,
            payment_method="gateway",
            discount_total=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            placed_at=now - timedelta(days=i),
            grand_total=amount,
        )

    url = reverse("backoffice:sales_api")
    resp = client.get(url, {"days": 7}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, dict)
    assert "labels" in data and isinstance(data["labels"], list)
    assert "datasets" in data and isinstance(data["datasets"], list)
    assert len(data["datasets"]) >= 1
    for ds in data["datasets"]:
        assert "label" in ds
        assert "data" in ds and isinstance(ds["data"], list)

    # Should not be all-empty because we created 3 paid orders
    assert any(ds["data"] for ds in data["datasets"])


@pytest.mark.django_db
@pytest.mark.parametrize("days", [1, 7, 30, 365, 400, "abc"])
def test_sales_api_days_param_is_robust(client, django_user_model, days):
    _make_staff_user(client, django_user_model)
    # No orders created → still must return valid (empty) schema
    url = reverse("backoffice:sales_api")
    resp = client.get(url, {"days": days})
    assert resp.status_code == 200
    payload = resp.json()
    assert "labels" in payload and "datasets" in payload
    assert isinstance(payload["labels"], list)
    assert isinstance(payload["datasets"], list)
    assert all("data" in ds for ds in payload["datasets"])


@pytest.mark.django_db
def test_sales_api_smoke_minimal_data(client, django_user_model):
    staff = _make_staff_user(client, django_user_model)
    customer, shipping_address, shipping_attname = _ensure_customer_and_shipping(staff)

    Order.objects.create(
        customer=customer,
        **{shipping_attname: shipping_address.pk},
        status=OrderStatus.PAID,
        placed_at=timezone.now(),
        grand_total=Decimal("100.00"),
        payment_method="gateway",
        discount_total=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
    )

    url = reverse("backoffice:sales_api") + "?days=7"
    resp = client.get(url)
    assert resp.status_code == 200
    payload = json.loads(resp.content)
    assert "labels" in payload and "datasets" in payload


# ---------- Optional sanity checks for related views (quick smoke) ----------


@pytest.mark.django_db
def test_reports_view_smoke_and_csv_schema(client, django_user_model):
    _make_staff_user(client, django_user_model)

    # HTML reports page
    url = reverse("backoffice:reports")
    resp = client.get(url, {"start": timezone.localdate(), "end": timezone.localdate()})
    assert resp.status_code == 200

    # CSV export must be valid CSV with at least header
    url = reverse("backoffice:export_sales_csv")
    resp = client.get(url, {"start": timezone.localdate(), "end": timezone.localdate()})
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    reader = csv.reader(io.StringIO(resp.content.decode("utf-8")))
    rows = list(reader)
    assert rows and rows[0] == ["date", "sales"]
