# apps/backoffice/views.py
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.orders.models import Order, OrderItem, OrderStatusLog

from .permissions import staff_required
from .services import daily_sales, kpis


def health(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@staff_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    # ❗️ NOTE: Prefetch با slicing مجاز نیست؛ پس بدون [:3] بگذار و توی تمپلیت slice کن.
    recent_orders = (
        Order.objects.select_related("user")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("product")))
        .order_by("-placed_at")[:10]
    )

    context = {
        "recent_orders": recent_orders,
        # اگر KPIها را جای دیگری حساب می‌کنید، همان را پاس بدهید یا از kpis_api فرانت بگیرد.
        # "kpis": kpis(),
        # بهتر از build_absolute_uri اینه که از reverse استفاده کنیم:
        "sales_api_url": request.build_absolute_uri(reverse("backoffice:sales_api")),
        "set_status_url_name": "backoffice:set_status",  # برای تمپلیت
    }
    return render(request, "backoffice/dashboard.html", context)


@staff_required
def kpis_api(request: HttpRequest) -> JsonResponse:
    return JsonResponse(kpis())


@staff_required
def sales_api(request: HttpRequest) -> JsonResponse:
    """
    Return Chart.js-friendly payload:
      {
        "labels": [...],
        "datasets": [
          {"label": "Revenue (€)", "data": [...]},
          {"label": "Orders", "data": [...]}
        ]
      }
    """
    days = int(request.GET.get("days", 30))
    # Assumption: daily_sales(days) -> list of dicts like:
    # [{"date": "YYYY-MM-DD", "revenue": float, "orders": int}, ...]
    series = daily_sales(days)

    labels = [row["date"] for row in series]
    revenue_data = [row.get("revenue", 0) for row in series]
    orders_data = [row.get("orders", 0) for row in series]

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

    # اگر Order.STATUS_CHOICES دارید:
    if new_status not in dict(order.STATUS_CHOICES):
        messages.error(request, "Invalid status")
        return redirect("backoffice:dashboard")

    prev = order.status
    if prev != new_status:
        order.status = new_status
        order.save(update_fields=["status"])
        OrderStatusLog.objects.create(
            order=order,
            changed_by=request.user if request.user.is_authenticated else None,
            from_status=prev,
            to_status=new_status,
        )

    messages.success(request, f"Order {order.number} status → {new_status}")
    return redirect("backoffice:dashboard")


# 2) حالت AJAX (JSON) برای اینلاین در جدول
@staff_member_required
@require_POST
def set_status_view(request: HttpRequest, order_id: int) -> JsonResponse:
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")

    if new_status not in dict(order.STATUS_CHOICES):
        return HttpResponseBadRequest("invalid status")

    prev = order.status
    if prev != new_status:
        order.status = new_status
        order.save(update_fields=["status"])
        OrderStatusLog.objects.create(
            order=order,
            changed_by=request.user if request.user.is_authenticated else None,
            from_status=prev,
            to_status=new_status,
        )

    badge_html = render_to_string(
        "backoffice/partials/_order_status_badge.html",
        {"status": order.status},
        request=request,
    )
    return JsonResponse({"ok": True, "status": order.status, "badge_html": badge_html})
