from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Prefetch
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.orders.models import Order, OrderItem, OrderStatusLog
from apps.orders.services import (
    get_orders_counters,
    get_sales_kpis,
    get_sales_timeseries_by_day,
    get_users_counters,
)

from .permissions import staff_required
from .services import kpis


# -----------------------------
# Small helpers
# -----------------------------
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
    # normalize (swap) if user sent reversed range
    if start > end:
        start, end = end, start
    return start, end


# -----------------------------
# Health
# -----------------------------
@require_GET
def health(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


# -----------------------------
# Dashboard
# -----------------------------
@staff_required
@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    # NOTE: Prefetch with slicing is not allowed → slice only on the main queryset.
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
@require_GET
def kpis_api(_: HttpRequest) -> JsonResponse:
    return JsonResponse(kpis())


# -----------------------------
# Sales API (Chart.js payload)
# -----------------------------
@staff_member_required
@require_GET
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
    # Guard & clamp 'days' (reasonable bounds to avoid heavy queries)
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))

    end = timezone.localdate()
    start = end - timezone.timedelta(days=days - 1)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    # empty but valid
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

    # dynamic keys (date/label), (revenue/amount/total), (orders/count/…)
    first = series[0]
    date_key = _detect_key(first, ("date", "day", "label"))
    revenue_key = _detect_key(first, ("revenue", "total", "amount", "sum"))
    orders_key = _detect_key(first, ("orders", "count", "order_count"))

    labels: list[str] = []
    revenue_data: list[float] = []
    orders_data: list[int] = []

    for row in series:
        labels.append(str(row.get(date_key, "")) if date_key else "")

        # revenue → float
        rev = row.get(revenue_key, 0) if revenue_key else 0
        try:
            revenue_data.append(float(rev))
        except Exception:
            revenue_data.append(0.0)

        # orders → int (safe cast)
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
    }
    return JsonResponse(payload)


# -----------------------------
# Status change (non-AJAX redirect)
# -----------------------------
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
            # logging here (optional)
            pass

    messages.success(
        request,
        f"Order {getattr(order, 'number', order.pk)} status → {new_status}",
    )
    return redirect("backoffice:dashboard")


def _allowed_status_values(order: Order) -> list[str]:
    """
    Priority:
    1) Field 'status'.choices
    2) Order.Status enum
    3) STATUS_CHOICES legacy
    """
    # 1) choices on field
    try:
        field = order._meta.get_field("status")
        choices: Iterable[tuple[str, str]] | None = getattr(field, "choices", None)  # type: ignore[assignment]
        if choices:
            return [c[0] for c in choices]
    except FieldDoesNotExist:
        pass

    # 2) inner Enum
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

    # 3) legacy STATUS_CHOICES
    if hasattr(order, "STATUS_CHOICES"):
        try:
            return [c[0] for c in order.STATUS_CHOICES]  # type: ignore[attr-defined]
        except Exception:
            pass

    # 4) no explicit restriction
    return []


# -----------------------------
# Status change (AJAX)
# -----------------------------
@staff_member_required
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
            # optional: log
            pass

    badge_html = render_to_string(
        "backoffice/partials/_order_status_badge.html",
        {"status": getattr(order, "status", new_status)},
        request=request,
    )
    return JsonResponse(
        {"ok": True, "status": getattr(order, "status", new_status), "badge_html": badge_html}
    )


# -----------------------------
# Reports & CSV export
# -----------------------------
@staff_member_required
@require_GET
def reports_view(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    start, end = _parse_date_range_from_request(request, default_start, default_end)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    # series items expected to have {"label": "...", "value": number}
    total_sum = 0.0
    for p in series:
        try:
            total_sum += float(p.get("value", 0) or 0)
        except Exception:
            pass

    context = {
        "start": start,
        "end": end,
        "series": series,
        "total_sum": total_sum,
    }
    return render(request, "backoffice/reports.html", context)


@staff_member_required
@require_GET
def export_sales_csv_view(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    start, end = _parse_date_range_from_request(request, default_start, default_end)
    series: list[dict[str, Any]] = get_sales_timeseries_by_day(start, end) or []

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="sales_{start}_to_{end}.csv"'

    # Explicit lineterminator avoids double newlines on Windows
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
