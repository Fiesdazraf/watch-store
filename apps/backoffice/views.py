from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.invoices.models import Invoice
from apps.orders.models import Order, OrderItem, OrderStatusLog
from apps.orders.services import (
    get_orders_counters,
    get_sales_kpis,
    get_sales_timeseries_by_day,
    get_users_counters,
)

from .permissions import staff_required

# services.kpis را طوری ایمپورت می‌کنیم که اگر در دسترس نبود، باز هم ماژول لود شود
try:
    from .services import kpis as _kpis_service
except Exception:
    _kpis_service = None  # type: ignore[assignment]

# Optional deps
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# ----------------------------- helpers -----------------------------
def _detect_key(
    d: dict[str, Any], candidates: tuple[str, ...], default: str | None = None
) -> str | None:
    for k in candidates:
        if k in d:
            return k
    return default


def _parse_yyyy_mm_dd(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_date_range_from_request(
    request: HttpRequest,
    default_start: date,
    default_end: date,
) -> tuple[date, date]:
    start = _parse_yyyy_mm_dd(request.GET.get("start")) or default_start
    end = _parse_yyyy_mm_dd(request.GET.get("end")) or default_end
    if start > end:  # normalize (swap)
        start, end = end, start
    return start, end


def _allowed_status_values(order: Order) -> list[str]:
    """
    Priority:
    1) Field 'status'.choices
    2) Order.Status enum
    3) STATUS_CHOICES legacy
    """
    try:
        field = order._meta.get_field("status")
        choices: Iterable[tuple[str, str]] | None = getattr(field, "choices", None)  # type: ignore[assignment]
        if choices:
            return [c[0] for c in choices]
    except FieldDoesNotExist:
        pass

    StatusEnum = getattr(order.__class__, "Status", None)
    if StatusEnum is not None:
        vals: list[str] = []
        for name in dir(StatusEnum):
            if name.startswith("_"):
                continue
            val = getattr(StatusEnum, name)
            if isinstance(val, (str, int)):
                vals.append(str(val))
        if vals:
            return vals

    if hasattr(order, "STATUS_CHOICES"):
        try:
            return [c[0] for c in order.STATUS_CHOICES]  # type: ignore[attr-defined]
        except Exception:
            pass

    return []


# ----------------------------- Health -----------------------------
@require_GET
def health(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@staff_required
@require_GET
def invoices_list_view(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    st = (request.GET.get("status") or "").strip()
    start = request.GET.get("start")
    end = request.GET.get("end")

    qs = Invoice.objects.select_related("order").order_by("-issued_at")

    if q:
        # 🔍 جستجو بر اساس شماره فاکتور یا شماره سفارش یا ID سفارش
        qs = qs.filter(
            Q(number__icontains=q) | Q(order__number__icontains=q) | Q(order__id__icontains=q)
        )

    if st:
        qs = qs.filter(status=st)
    if start:
        qs = qs.filter(issued_at__date__gte=start)
    if end:
        qs = qs.filter(issued_at__date__lte=end)

    context = {
        "query": q,
        "status": st,
        "start": start or "",
        "end": end or "",
        "invoices": qs[:200],  # limit results for simplicity
    }
    return render(request, "backoffice/invoices_list.html", context)


# ----------------------------- Dashboard -----------------------------
@staff_required
@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    start = request.GET.get("start") or ""
    end = request.GET.get("end") or ""
    status = request.GET.get("status") or ""

    recent_orders = (
        Order.objects.select_related("customer", "customer__user")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("product")))
        .order_by("-placed_at")[:10]
    )

    sales_kpis = get_sales_kpis()
    orders_counters = get_orders_counters()
    users_counters = get_users_counters()
    invoices_counters = get_invoices_counters()  # 👈 اضافه شد
    recent_invoices = Invoice.objects.order_by("-issued_at")[:10]  # 👈 جدول جدید

    context = {
        "recent_orders": recent_orders,
        "recent_invoices": recent_invoices,  # 👈 اضافه شد
        "sales_api_url": request.build_absolute_uri(reverse("backoffice:sales_api")),
        "set_status_url_name": "backoffice:set_status",
        "sales_kpis": sales_kpis,
        "orders_counters": orders_counters,
        "users_counters": users_counters,
        "invoices_counters": invoices_counters,  # 👈 اضافه شد
        "now": timezone.now(),
        "kpi_filters": {"start": start, "end": end, "status": status},
    }
    return render(request, "backoffice/dashboard.html", context)


# ----------------------------- Invoices KPI helper -----------------------------
def get_invoices_counters() -> dict:
    """Aggregated stats for invoices (used in dashboard KPIs)."""
    total = Invoice.objects.count()
    total_amount = Invoice.objects.aggregate(total=Sum("amount"))["total"] or 0
    paid = Invoice.objects.filter(status="paid").count()
    unpaid = Invoice.objects.exclude(status="paid").count()
    paid_ratio = round((paid / total) * 100, 1) if total else 0

    return {
        "total": total,
        "total_amount": total_amount,
        "paid": paid,
        "unpaid": unpaid,
        "paid_ratio": paid_ratio,
    }


# ----------------------------- KPIs API -----------------------------
@staff_required
@require_GET
def kpis_api(_: HttpRequest) -> JsonResponse:
    """
    Returns aggregated KPIs for the dashboard.
    Falls back to local composition if services.kpis is unavailable.
    """
    if callable(_kpis_service):
        try:
            return JsonResponse(_kpis_service())
        except Exception:
            pass  # fallback below

    # --- Local KPI composition ---
    data = {
        "sales_kpis": get_sales_kpis(),
        "orders_counters": get_orders_counters(),
        "users_counters": get_users_counters(),
        "invoices_counters": get_invoices_counters(),  # 👈 اضافه شد
    }
    return JsonResponse(data)


# ----------------------------- Sales API (Chart.js payload) -----------------------------
@staff_required
@require_GET
def sales_api(request: HttpRequest) -> JsonResponse:
    """
    Returns Chart.js-friendly payload:
    {
      "labels": [...],
      "datasets": [
        {"label": "Revenue (€)", "data": [...]},
        {"label": "Orders", "data": [...]}
      ],
      // backward-compat:
      "amounts": [...],
      "counts": [...]
    }
    """
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))

    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    if not series:
        return JsonResponse(
            {
                "labels": [],
                "datasets": [
                    {"label": "Revenue (€)", "data": []},
                    {"label": "Orders", "data": []},
                ],
                "amounts": [],
                "counts": [],
            }
        )

    first = series[0]
    date_key = _detect_key(first, ("date", "day", "label"))
    revenue_key = _detect_key(first, ("revenue", "total", "amount", "sum"))
    orders_key = _detect_key(first, ("orders", "count", "order_count"))

    labels: list[str] = []
    revenue_data: list[float] = []
    orders_data: list[int] = []

    for row in series:
        labels.append(str(row.get(date_key, "")) if date_key else "")

        rev = row.get(revenue_key, 0) if revenue_key else 0
        try:
            revenue_data.append(float(rev))
        except Exception:
            revenue_data.append(0.0)

        cnt = row.get(orders_key, 0) if orders_key else 0
        try:
            orders_data.append(int(cnt))
        except Exception:
            try:
                orders_data.append(int(float(cnt)))
            except Exception:
                orders_data.append(0)

    payload = {
        "labels": labels,
        "datasets": [
            {"label": "Revenue (€)", "data": revenue_data},
            {"label": "Orders", "data": orders_data},
        ],
        # backward-compat for older frontend
        "amounts": revenue_data,
        "counts": orders_data,
    }
    return JsonResponse(payload)


# ----------------------------- Status change -----------------------------
@staff_required
@require_POST
def set_status_redirect_view(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")
    if not new_status:
        messages.error(request, "Missing status")
        return redirect("backoffice:dashboard")

    allowed = _allowed_status_values(order)
    if allowed and new_status not in allowed:
        messages.error(request, "Invalid status")
        return redirect("backoffice:dashboard")

    prev = getattr(order, "status", None)
    if prev != new_status:
        order.status = new_status  # type: ignore[attr-defined]
        order.save(update_fields=["status"])
        try:
            OrderStatusLog.objects.create(
                order=order,
                changed_by=request.user if request.user.is_authenticated else None,
                from_status=prev or "",
                to_status=new_status,
            )
        except Exception:
            pass

    messages.success(request, f"Order {getattr(order, 'number', order.pk)} status → {new_status}")
    return redirect("backoffice:dashboard")


@staff_required
@require_POST
def set_status_view(request: HttpRequest, order_id: int) -> JsonResponse:
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")
    if new_status is None:
        return HttpResponseBadRequest("missing status")

    allowed = _allowed_status_values(order)
    if allowed and new_status not in allowed:
        return HttpResponseBadRequest("invalid status")

    prev = getattr(order, "status", None)
    if prev != new_status:
        order.status = new_status  # type: ignore[attr-defined]
        order.save(update_fields=["status"])
        try:
            OrderStatusLog.objects.create(
                order=order,
                changed_by=request.user if request.user.is_authenticated else None,
                from_status=prev or "",
                to_status=new_status,
            )
        except Exception:
            pass

    badge_html = render_to_string(
        "backoffice/partials/_order_status_badge.html",
        {"status": getattr(order, "status", new_status)},
        request=request,
    )
    return JsonResponse(
        {"ok": True, "status": getattr(order, "status", new_status), "badge_html": badge_html}
    )


# ----------------------------- Reports & CSV export -----------------------------
staff_required


@require_GET
def reports_view(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    kpis = Invoice.objects.kpis()
    start, end = _parse_date_range_from_request(request, default_start, default_end)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    total_sum = sum(float(p.get("value", 0) or 0) for p in series)

    context = {
        "start": start,
        "end": end,
        "series": series,
        "total_sum": total_sum,
        "kpis": kpis,
    }
    return render(request, "backoffice/reports.html", context)


@staff_required
@require_GET
def invoices_api(request: HttpRequest) -> JsonResponse:
    """Return monthly invoice stats as JSON for charts"""
    data = (
        Invoice.objects.annotate(month=TruncMonth("issued_at"))
        .values("month")
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
            paid=Count("id", filter=Q(status="paid")),
        )
        .order_by("month")
    )
    return JsonResponse(list(data), safe=False)


@staff_required
@require_GET
def export_sales_csv_view(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    start, end = _parse_date_range_from_request(request, default_start, default_end)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="sales_{start}_to_{end}.csv"'

    writer = csv.writer(resp, lineterminator="\n")
    writer.writerow(["date", "sales"])
    for p in series:
        label = str(p.get("label", ""))
        try:
            val = float(p.get("value", 0) or 0)
        except Exception:
            val = 0.0
        writer.writerow([label, f"{val:.2f}"])
    return resp


# ----------------------------- XLSX / PDF Exports -----------------------------
@staff_required
@require_GET
def export_sales_xlsx_view(request: HttpRequest) -> HttpResponse:
    qs = Order.objects.select_related("customer").all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    status = request.GET.get("status")
    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)
    if status:
        qs = qs.filter(status=status)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["ID", "Number", "Customer", "Status", "Grand Total", "Placed At"])

    for o in qs.order_by("-placed_at"):
        ws.append(
            [
                o.id,
                o.number,
                getattr(o.customer, "email", "") if o.customer_id else "",
                o.status,
                float(o.grand_total or 0),
                o.placed_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="sales_{start or "all"}_{end or "all"}.xlsx"'
    )
    return resp


@staff_required
@require_GET
def export_sales_pdf_view(request: HttpRequest) -> HttpResponse:
    qs = Order.objects.all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Sales Report")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Range: {start or '—'} to {end or '—'}")
    y -= 30

    headers = ["#", "Number", "Status", "Total", "Placed At"]
    x_positions = [40, 90, 220, 300, 360]
    for i, h in enumerate(headers):
        c.drawString(x_positions[i], y, h)
    y -= 15
    c.line(40, y, width - 40, y)
    y -= 10

    for o in qs.order_by("-placed_at")[:500]:
        row = [
            str(o.id),
            o.number,
            o.status,
            f"{o.grand_total}",
            o.placed_at.strftime("%Y-%m-%d %H:%M"),
        ]
        if y < 60:
            c.showPage()
            y = height - 50
        for i, col in enumerate(row):
            c.drawString(x_positions[i], y, col)
        y -= 15

    c.save()
    pdf = buf.getvalue()
    buf.close()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="sales_{start or "all"}_{end or "all"}.pdf"'
    )
    return resp


# ----------------------------- Extra Chart APIs -----------------------------
@staff_required
@require_GET
def payments_breakdown_api(request: HttpRequest) -> JsonResponse:
    qs = Order.objects.all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    status = request.GET.get("status")

    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)
    if status:
        qs = qs.filter(status=status)

    agg = (
        qs.values("payment_method")
        .annotate(count=Count("id"), total=Sum("grand_total"))
        .order_by("-count")
    )
    labels = [row["payment_method"] or "—" for row in agg]
    counts = [row["count"] for row in agg]
    totals = [float(row["total"] or 0) for row in agg]

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {"label": "Orders", "data": counts},
                {"label": "Total Amount", "data": totals},
            ],
        }
    )


@staff_required
@require_GET
def orders_status_api(request: HttpRequest) -> JsonResponse:
    qs = Order.objects.all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)

    agg = qs.values("status").annotate(count=Count("id")).order_by("-count")
    labels = [row["status"] for row in agg]
    values = [row["count"] for row in agg]

    return JsonResponse(
        {"labels": labels, "datasets": [{"label": "Orders by Status", "data": values}]}
    )
