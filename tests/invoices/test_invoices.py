import pytest
from django.db import connection

from apps.accounts.models import User
from apps.customers.models import Address, Customer
from apps.invoices.services import create_invoice_for_order
from apps.orders.models import Order


@pytest.mark.django_db(transaction=True)
def test_invoice_creation_from_order():
    # 💣 پاک‌سازی امن (برای اطمینان از دیتابیس تمیز)
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("DELETE FROM invoices_invoice;")
        cursor.execute("DELETE FROM orders_order;")
        cursor.execute("DELETE FROM customers_customer;")
        cursor.execute("DELETE FROM accounts_user;")
        cursor.execute("DELETE FROM sqlite_sequence;")
        cursor.execute("PRAGMA foreign_keys = ON;")

    # ✅ ساخت user جدید
    user = User.objects.create(email="invoice_test_user@example.com", full_name="Invoice User")

    # ⚙️ customer مرتبط (اگر وجود داشت، دوباره استفاده می‌کنه)
    customer, _ = Customer.objects.get_or_create(user=user)

    # 🏠 آدرس تست برای فیلد الزامی shipping_address
    address = Address.objects.create(
        user=user,
        full_name="Test User",
        line1="123 Test Street",
        city="TestCity",
        postal_code="12345",
        country="IR",
        default_shipping=True,
    )

    # ✅ ساخت سفارش با فیلد واقعی grand_total
    order = Order.objects.create(
        customer=customer,
        shipping_address=address,
        grand_total=200000,
        status="paid",
        payment_method="fake",
    )

    # ✅ ساخت فاکتور برای سفارش
    invoice = create_invoice_for_order(order)

    # 🧾 بررسی
    assert invoice.order == order
    assert invoice.amount == order.grand_total
    assert invoice.status == "paid"
