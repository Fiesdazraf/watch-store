from decimal import Decimal

import pytest
from django.db import models as djm
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order, OrderStatus


def _build_instance_kwargs(model, owner_user=None, owner_customer=None):
    kwargs = {}
    for f in model._meta.get_fields():
        if not isinstance(f, djm.Field) or f.auto_created:
            continue
        if f.name == "id":
            continue
        if getattr(f, "null", False) or f.has_default():
            continue

        if f.is_relation:
            if f.name in ("user", "customer"):
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
def test_backoffice_set_status_ajax_updates_badge(client, django_user_model):
    staff = django_user_model.objects.create_user(
        email="staff@test.com", password="pass", is_staff=True
    )
    client.force_login(staff)

    customer, _ = Customer.objects.get_or_create(user=staff)

    # مدل آدرس مرتبط با Order را داینامیک بگیر
    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=staff, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)

    # 👇 به‌جای shipping_address=... از attname استفاده کن
    order_kwargs = {
        "customer": customer,
        shipping_field.attname: shipping_address.pk,  # e.g. "shipping_address_id"
        "status": OrderStatus.PENDING,
        "payment_method": "gateway",
        "discount_total": 0,
        "shipping_cost": 0,
    }
    order = Order.objects.create(**order_kwargs)

    url = reverse("backoffice:set_status", args=[order.id])
    resp = client.post(url, {"status": OrderStatus.PAID}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == OrderStatus.PAID
    assert "badge_html" in data and isinstance(data["badge_html"], str)

    order.refresh_from_db()
    assert order.status == OrderStatus.PAID
