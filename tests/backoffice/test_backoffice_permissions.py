from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import models as djm
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order, OrderStatus

# --- helpers (همان الگو با sales_api) ---


def _build_instance_kwargs(model, owner_user=None, owner_customer=None) -> dict[str, Any]:
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


def _ensure_customer_and_shipping(user):
    customer, _ = Customer.objects.get_or_create(user=user)
    shipping_field = Order._meta.get_field("shipping_address")
    ShippingAddressModel = shipping_field.remote_field.model
    addr_kwargs = _build_instance_kwargs(
        ShippingAddressModel, owner_user=user, owner_customer=customer
    )
    shipping_address = ShippingAddressModel.objects.create(**addr_kwargs)
    return customer, shipping_address, shipping_field.attname


@pytest.mark.django_db
def test_set_status_requires_staff(client, django_user_model):
    # 1) کاربر غیر استاف (لاگین شده)
    user = django_user_model.objects.create_user(
        **{getattr(django_user_model, "USERNAME_FIELD", "email"): "u@test.com"},
        password="x",
        is_staff=False,
    )
    client.force_login(user)

    # 2) ساخت یک سفارش مینیمم که بتوان رویش set-status زد
    customer, shipping_address, shipping_attname = _ensure_customer_and_shipping(user)
    order = Order.objects.create(
        customer=customer,
        **{shipping_attname: shipping_address.pk},
        status=OrderStatus.NEW if hasattr(OrderStatus, "NEW") else "new",
        placed_at=timezone.now() - timedelta(days=1),
        grand_total=Decimal("100.00"),
        payment_method="gateway",
        discount_total=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
    )

    # 3) تلاش برای POST به endpoint بدون Staff بودن
    url = reverse("backoffice:set_status", args=[order.pk])
    resp = client.post(url, {"status": "paid"})
    # باید دسترسی نده (یا redirect به login یا 403)
    assert resp.status_code in (302, 403)
