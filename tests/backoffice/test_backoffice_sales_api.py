# tests/backoffice/test_backoffice_sales_api.py
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import models as djm
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order, OrderStatus


def _build_instance_kwargs(model, owner_user=None, owner_customer=None):
    """Fill minimal NOT NULL fields for address-like models, without hard assumptions."""
    kwargs = {}
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
        if isinstance(f, djm.CharField) or isinstance(f, djm.TextField):
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
def test_sales_api_returns_labels_and_datasets(client, django_user_model):
    staff = django_user_model.objects.create_user(
        email="staff@test.com", password="pass", is_staff=True
    )
    client.force_login(staff)

    # Customer
    customer, _ = Customer.objects.get_or_create(user=staff)

    # Address model & instance (via Order.shipping_address FK)
    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=staff, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)

    # Create 3 paid orders in the last 3 days with grand_total > 0
    now = timezone.now()
    amounts = [Decimal("100.00"), Decimal("200.00"), Decimal("300.00")]
    for i, amount in enumerate(amounts):
        Order.objects.create(
            customer=customer,
            **{shipping_field.attname: shipping_address.pk},  # FK via attname
            status=OrderStatus.PAID,
            payment_method="gateway",
            discount_total=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            placed_at=now - timedelta(days=i),
            grand_total=amount,  # IMPORTANT for revenue series
        )

    url = reverse("backoffice:sales_api")
    resp = client.get(url, {"days": 7}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert resp.status_code == 200

    data = resp.json()
    assert "labels" in data and isinstance(data["labels"], list)
    assert "datasets" in data and isinstance(data["datasets"], list)
    for ds in data["datasets"]:
        assert "label" in ds and "data" in ds and isinstance(ds["data"], list)
    # Should not be all empty because we created 3 orders
    assert any(ds["data"] for ds in data["datasets"])


@pytest.mark.django_db
def test_sales_api_smoke(client, admin_user):
    client.force_login(admin_user)

    # minimal customer + shipping address (Order.customer is NOT NULL)
    customer, _ = Customer.objects.get_or_create(user=admin_user)

    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=admin_user, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)

    now = timezone.now()
    Order.objects.create(
        customer=customer,
        **{shipping_field.attname: shipping_address.pk},
        status=OrderStatus.PAID,
        placed_at=now,
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
