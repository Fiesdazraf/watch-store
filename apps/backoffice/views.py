# apps/backoffice/views.py
import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.orders.models import Order, OrderItem, OrderStatusLog
from apps.orders.services import (
    get_orders_counters,
    get_sales_kpis,
    get_sales_timeseries_by_day,
    get_users_counters,
)

from .permissions import staff_required
from .services import kpis


def health(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@staff_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    # ❗️ NOTE: Prefetch با slicing مجاز نیست؛ پس بدون [:3] بگذار و توی تمپلیت slice کن.
    recent_orders = (
        Order.objects.select_related("customer", "customer__user")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product"),
            )
        )
        .order_by("-placed_at")[:10]
    )

    context = {
        "recent_orders": recent_orders,
        "sales_api_url": request.build_absolute_uri(reverse("backoffice:sales_api")),
        "set_status_url_name": "backoffice:set_status",
        "sales_kpis": get_sales_kpis(),
        "orders_counters": get_orders_counters(),
        "users_counters": get_users_counters(),
        "now": timezone.now(),
    }
    return render(request, "backoffice/dashboard.html", context)


@staff_required
def kpis_api(request: HttpRequest) -> JsonResponse:
    return JsonResponse(kpis())


def _detect_key(d: dict, candidates: tuple[str, ...], default: str | None = None) -> str | None:
    for k in candidates:
        if k in d:
            return k
    return default


@staff_member_required
def sales_api(request: HttpRequest) -> JsonResponse:
    """
    Returns Chart.js-friendly payload:
    {
      "labels": [...],
      "datasets": [
        {"label": "Revenue (€)", "data": [...]},
        {"label": "Orders", "data": [...]}
      ]
    }
    """
    days = int(request.GET.get("days", 30))
    end = timezone.localdate()
    start = end - timezone.timedelta(days=days - 1)
    series = get_sales_timeseries_by_day(start, end)
    # اگر خالی بود، خروجی خالی اما معتبر بده
    if not series:
        return JsonResponse(
            {
                "labels": [],
                "datasets": [
                    {"label": "Revenue (€)", "data": []},
                    {"label": "Orders", "data": []},
                ],
            }
        )

    first = series[0] if isinstance(series, list) else {}
    # تشخیص داینامیک کلیدها (date/day/label) و (revenue/total/amount) و (orders/count/order_count)
    date_key = _detect_key(first, ("date", "day", "label"))
    revenue_key = _detect_key(first, ("revenue", "total", "amount", "sum"))
    orders_key = _detect_key(first, ("orders", "count", "order_count"))

    # ساخت labels و datasets با محافظه‌کاری (بدون KeyError)
    labels = []
    revenue_data = []
    orders_data = []

    for row in series:
        # تاریخ/برچسب
        labels.append(str(row.get(date_key, "")) if date_key else "")
        # درآمد
        revenue_val = row.get(revenue_key, 0) if revenue_key else 0
        try:
            revenue_val = float(revenue_val)
        except Exception:
            revenue_val = 0.0
        revenue_data.append(revenue_val)
        # تعداد سفارش
        orders_val = row.get(orders_key, 0) if orders_key else 0
        try:
            orders_val = int(orders_val)
        except Exception:
            # اگر عدد اعشاری بود یا رشته، به int امن تبدیل کن
            try:
                orders_val = int(float(orders_val))
            except Exception:
                orders_val = 0
        orders_data.append(orders_val)

    payload = {
        "labels": labels,
        "datasets": [
            {"label": "Revenue (€)", "data": revenue_data},
            {"label": "Orders", "data": orders_data},
        ],
    }
    return JsonResponse(payload)


# --- دو مسیر برای تغییر وضعیت:
# 1) حالت معمولی (Redirect + messages) برای submit فرم غیر-AJAX
@staff_required
@require_POST
def set_status_redirect_view(request: HttpRequest, order_id: int):
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


def _allowed_status_values(order: Order) -> list:
    """
    اول از choices خود فیلد status استفاده می‌کنیم.
    اگر نبود، از Enum داخلی Order.Status.
    در نهایت اگر STATUS_CHOICES قدیمی وجود داشت از آن.
    اگر هیچ‌کدام نبود، لیست خالی یعنی محدودیت صریحی نداریم.
    """
    # 1) choices روی فیلد
    try:
        field = order._meta.get_field("status")
        if getattr(field, "choices", None):
            return [c[0] for c in field.choices]
    except FieldDoesNotExist:
        pass

    # 2) Enum داخلی
    StatusEnum = getattr(order.__class__, "Status", None)
    if StatusEnum is not None:
        vals = []
        for name in dir(StatusEnum):
            if name.startswith("_"):
                continue
            val = getattr(StatusEnum, name)
            if isinstance(val, (str, int)):
                vals.append(val)
        if vals:
            return vals

    # 3) الگوی قدیمی
    if hasattr(order, "STATUS_CHOICES"):
        try:
            return [c[0] for c in order.STATUS_CHOICES]  # type: ignore[attr-defined]
        except Exception:
            pass

    # 4) بدون محدودیت صریح
    return []


@staff_member_required
@require_POST
def set_status_view(request: HttpRequest, order_id: int) -> JsonResponse:
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")

    if new_status is None:
        return HttpResponseBadRequest("missing status")

    allowed = _allowed_status_values(order)
    # اگر allowed خالی نبود، اعتبارسنجی کن؛ اگر خالی بود یعنی آزادی عمل داریم
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
            # اگر مدل لاگ نداری یا اختیاریه، جلوی خطا را می‌گیریم تا جریان UI نشکند
            pass

    badge_html = render_to_string(
        "backoffice/partials/_order_status_badge.html",
        {"status": getattr(order, "status", new_status)},
        request=request,
    )
    return JsonResponse(
        {"ok": True, "status": getattr(order, "status", new_status), "badge_html": badge_html}
    )


# apps/backoffice/views.py (append)


@staff_member_required
def reports_view(request):
    # Parse date filters (YYYY-MM-DD)
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else default_start
        end = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else default_end
    except ValueError:
        start, end = default_start, default_end

    series = get_sales_timeseries_by_day(start, end)

    context = {
        "start": start,
        "end": end,
        "series": series,
        "total_sum": sum(p["value"] for p in series),
    }
    return render(request, "backoffice/reports.html", context)


@staff_member_required
def export_sales_csv_view(request):
    # Same parsing as reports_view to keep export in sync
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else default_start
        end = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else default_end
    except ValueError:
        start, end = default_start, default_end

    series = get_sales_timeseries_by_day(start, end)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="sales_{start}_to_{end}.csv"'

    writer = csv.writer(resp)
    writer.writerow(["date", "sales"])
    for p in series:
        writer.writerow([p["label"], f'{p["value"]:.2f}'])

    return resp
