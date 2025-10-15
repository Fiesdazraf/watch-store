from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.invoices.models import Invoice  # 👈 اضافه شد
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment

# سفارش «پرداخت‌شده»: یا خود سفارش status=PAID،
# یا رکورد Payment مرتبط با این سفارش status='paid' داشته باشد (بدون تکیه به related_name).
PAID_EXISTS = Exists(Payment.objects.filter(order_id=OuterRef("pk"), status__iexact="paid"))
PAID_Q = Q(status=OrderStatus.PAID) | PAID_EXISTS


def kpis():
    now = timezone.now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_30 = now - timedelta(days=30)

    # --- Orders & Sales KPIs ---
    qs_paid = Order.objects.filter(PAID_Q)
    qs_today = qs_paid.filter(placed_at__gte=start_today)
    revenue_today = qs_today.aggregate(s=Sum("grand_total"))["s"] or Decimal("0")

    qs_30 = qs_paid.filter(placed_at__gte=last_30)
    orders_30 = qs_30.count()
    revenue_30 = qs_30.aggregate(s=Sum("grand_total"))["s"] or Decimal("0")
    aov_30 = (revenue_30 / orders_30) if orders_30 else Decimal("0")

    # --- Invoices KPIs ---
    invoices_total = Invoice.objects.count()
    invoices_paid = Invoice.objects.filter(status="paid").count()
    invoices_unpaid = Invoice.objects.exclude(status="paid").count()
    invoices_total_amount = Invoice.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid_ratio = round((invoices_paid / invoices_total * 100), 1) if invoices_total else 0

    invoices_30 = Invoice.objects.filter(issued_at__gte=last_30)
    invoices_30_count = invoices_30.count()
    invoices_30_revenue = invoices_30.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    return {
        # ---- existing sales KPIs ----
        "orders_today": qs_today.count(),
        "revenue_today": revenue_today,
        "orders_30d": orders_30,
        "revenue_30d": revenue_30,
        "avg_order_value_30d": aov_30,
        # ---- new invoice KPIs ----
        "invoices_total": invoices_total,
        "invoices_paid": invoices_paid,
        "invoices_unpaid": invoices_unpaid,
        "invoices_total_amount": invoices_total_amount,
        "invoices_paid_ratio": paid_ratio,
        "invoices_30d": invoices_30_count,
        "invoices_revenue_30d": invoices_30_revenue,
    }


def daily_sales(last_days=30):
    now = timezone.now()
    since = now - timedelta(days=last_days)
    rows = (
        Order.objects.filter(PAID_Q, placed_at__gte=since)
        .annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(orders=Count("id"), revenue=Sum("grand_total"))
        .order_by("day")
    )
    return list(rows)
