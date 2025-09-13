from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Order

from .permissions import staff_required
from .services import daily_sales, kpis


@staff_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    data = kpis()
    return render(request, "backoffice/dashboard.html", {"kpis": data})


@staff_required
def kpis_api(request: HttpRequest) -> JsonResponse:
    return JsonResponse(kpis())


@staff_required
def sales_api(request: HttpRequest) -> JsonResponse:
    days = int(request.GET.get("days", 30))
    return JsonResponse({"series": daily_sales(days)})


@staff_required
def order_set_status_view(request, order_id):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")
    try:
        order.set_status(new_status, by_user=request.user)
        messages.success(request, f"Order {order.number} status → {new_status}")
        return redirect("backoffice:dashboard")
    except Exception as e:
        messages.error(request, str(e))
        return redirect("backoffice:dashboard")


def health(_):
    return HttpResponse("ok")
