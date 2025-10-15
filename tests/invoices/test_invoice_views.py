import pytest
from django.urls import reverse
from model_bakery import baker  # type: ignore

pytestmark = pytest.mark.django_db


def test_invoice_detail_requires_login(client):
    """کاربر لاگین‌نشده نباید بتواند فاکتور را ببیند."""
    invoice = baker.make("invoices.Invoice", number="INV001")
    url = reverse("invoices:invoice_detail", args=[invoice.number])
    resp = client.get(url)
    assert resp.status_code in (302, 403)  # redirect to login or forbidden


def test_invoice_detail_owner_or_staff_only(client):
    """فقط صاحب سفارش یا ادمین اجازه مشاهده دارد."""
    owner = baker.make("accounts.User")
    other = baker.make("accounts.User")
    staff = baker.make("accounts.User", is_staff=True)

    order = baker.make("orders.Order", customer__user=owner)
    invoice = baker.make("invoices.Invoice", number="INV002", order=order)

    url = reverse("invoices:invoice_detail", args=[invoice.number])

    # 1. کاربر غیرمالک
    client.force_login(other)
    resp = client.get(url)
    assert resp.status_code == 404

    # 2. مالک
    client.force_login(owner)
    resp = client.get(url)
    assert resp.status_code == 200
    assert str(invoice.number) in resp.content.decode()

    # 3. ادمین
    client.force_login(staff)
    resp = client.get(url)
    assert resp.status_code == 200


def test_invoice_pdf_download_ok(client):
    """دانلود PDF برای مالک یا ادمین باید موفق باشد."""
    user = baker.make("accounts.User")
    order = baker.make("orders.Order", customer__user=user)
    invoice = baker.make("invoices.Invoice", number="INV003", order=order)

    client.force_login(user)
    url = reverse("invoices:invoice_pdf", args=[invoice.number])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert invoice.number in resp["Content-Disposition"]
