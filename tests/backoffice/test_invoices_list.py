from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


# 🔇 fixture برای غیرفعال کردن signal ایجاد خودکار Customer
@pytest.fixture(autouse=True)
def disable_customer_signal():
    """Completely disable the Customer auto-create signal in all tests of this file."""
    from apps.customers.signals import create_customer_profile

    try:
        # disconnect signal (قطع اتصال واقعی)
        post_save.disconnect(receiver=create_customer_profile, sender=User)
    except Exception:
        pass

    # mock تابع داخل سیگنال (در صورت باقی ماندن reference)
    with patch("apps.customers.signals.create_customer_profile", lambda *a, **kw: None):
        yield

    # بازگرداندن signal برای سایر تست‌ها
    post_save.connect(create_customer_profile, sender=User)


# ============================================================
# TEST 1: دسترسی فقط برای ادمین
# ============================================================
def test_invoices_list_staff_only(client):
    """صفحه‌ی لیست فاکتورها فقط برای کاربر ادمین در دسترس است."""
    staff = baker.make("accounts.User", is_staff=True)
    user = baker.make("accounts.User")

    url = reverse("backoffice:invoices_list")

    # غیرادمین
    client.force_login(user)
    resp = client.get(url)
    assert resp.status_code in (302, 403)

    # ادمین
    client.force_login(staff)
    resp = client.get(url)
    assert resp.status_code == 200
    assert "فاکتورها" in resp.content.decode()


# ============================================================
# TEST 2: فیلترهای جستجو، وضعیت، تاریخ
# ============================================================
def test_filters_work(client):
    """فیلترهای جستجو، وضعیت و تاریخ باید درست کار کنند."""
    staff = baker.make("accounts.User", is_staff=True)
    client.force_login(staff)

    now = timezone.now()
    old = now - timedelta(days=60)

    user = baker.make("accounts.User")
    customer = baker.make("customers.Customer", user=user)
    address = baker.make("customers.Address", user=user)

    order1 = baker.make("orders.Order", customer=customer, shipping_address=address)
    order2 = baker.make("orders.Order", customer=customer, shipping_address=address)

    baker.make("invoices.Invoice", order=order1, number="INV-A", status="paid", issued_at=now)
    baker.make("invoices.Invoice", order=order2, number="INV-B", status="unpaid", issued_at=old)

    url = reverse("backoffice:invoices_list")

    # شماره
    resp = client.get(url, {"q": "INV-A"})
    assert "INV-A" in resp.content.decode()
    assert "INV-B" not in resp.content.decode()

    # وضعیت
    resp = client.get(url, {"status": "unpaid"})
    assert "INV-B" in resp.content.decode()
    assert "INV-A" not in resp.content.decode()

    # تاریخ
    resp = client.get(url, {"start": (now - timedelta(days=1)).date().isoformat()})
    assert "INV-A" in resp.content.decode()
    assert "INV-B" not in resp.content.decode()
