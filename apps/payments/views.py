# apps/payments/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.orders.models import Order
from apps.payments.models import PaymentStatus
from apps.payments.services import (
    can_retry,
    is_awaiting_payment,
    latest_payment,
    mark_payment_failed,
    mark_payment_success,
    start_cod_payment,
    start_fake_online_payment,
)


def _order_detail_url(order):
    """
    Try several common route names/kwargs to find an order detail url.
    Fallback to orders:list.
    """
    candidates = [
        ("orders:detail", {"number": getattr(order, "number", None)}),
        ("orders:detail", {"pk": getattr(order, "pk", None)}),
        ("orders:order_detail", {"number": getattr(order, "number", None)}),
        ("orders:order_detail", {"pk": getattr(order, "pk", None)}),
        ("orders:show", {"number": getattr(order, "number", None)}),
        ("orders:show", {"pk": getattr(order, "pk", None)}),
        ("orders:view", {"number": getattr(order, "number", None)}),
        ("orders:view", {"pk": getattr(order, "pk", None)}),
    ]
    for name, kwargs in candidates:
        # حذف None ها از kwargs
        kwargs = {k: v for k, v in (kwargs or {}).items() if v is not None}
        try:
            return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
        except NoReverseMatch:
            continue
    # fallback
    try:
        return reverse("orders:list")
    except NoReverseMatch:
        return "/"


@login_required
def checkout_payment_view(request, order_number: str):
    """
    - GET: نمایش صفحه انتخاب روش پرداخت
    - POST: خواندن request.POST['method'] در {'cod','online'} و شروع flow
    """
    order = get_object_or_404(Order, number=order_number, user=request.user)

    if not is_awaiting_payment(order):
        messages.info(request, "This order is not awaiting payment.")
        return redirect(_order_detail_url(order))

    if request.method == "POST":
        method = (request.POST.get("method") or "").strip().lower()
        if method not in {"cod", "online"}:
            messages.error(request, "Select a valid payment method.")
            return redirect("payments:checkout", order_number=order.number)

        if method == "cod":
            start_cod_payment(order)
            messages.success(request, "Order marked as paid (Cash on Delivery).")
            return redirect("payments:success", order_number=order.number)

        # method == "online"
        if not can_retry(order):
            messages.error(request, "حداکثر تلاش‌های پرداخت به پایان رسیده است.")
            return redirect("payments:checkout", order_number=order.number)
        _payment, redirect_url = start_fake_online_payment(order)
        return redirect(redirect_url)

    # GET
    return render(
        request,
        "payments/checkout_payment.html",
        {
            "order": order,
            "last_payment": latest_payment(order),
        },
    )


@login_required
@require_GET
def mock_gateway_view(request, order_number: str):
    """
    صفحه درگاه شبیه‌ساز با دکمه‌های:
    - Success -> payments:success
    - Fail    -> payments:failed
    """
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = latest_payment(order)
    if not payment:
        messages.error(request, "No payment session found.")
        return redirect("payments:checkout", order_number=order.number)

    return render(request, "payments/mock_gateway.html", {"order": order, "payment": payment})


@login_required
def payment_success_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = mark_payment_success(order)
    return render(
        request,
        "payments/payment_success.html",
        {
            "order": order,
            "payment": payment,
            "order_detail_url": _order_detail_url(order),  # ← NEW
        },
    )


@login_required
def payment_failed_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = mark_payment_failed(order)
    return render(
        request,
        "payments/payment_failed.html",
        {
            "order": order,
            "payment": payment,
            "order_detail_url": _order_detail_url(order),  # ← NEW
        },
    )


@login_required
def payment_canceled_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = latest_payment(order)
    if not payment:
        messages.error(request, "No payment found for this order.")
        return redirect(_order_detail_url(order))
    if payment.status != PaymentStatus.CANCELED:
        payment.status = PaymentStatus.CANCELED
        payment.save(update_fields=["status", "updated_at"])
    return render(
        request,
        "payments/payment_failed.html",
        {
            "order": order,
            "payment": payment,
            "order_detail_url": _order_detail_url(order),  # ← NEW
        },
    )
