# apps/payments/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from apps.orders.models import Order
from apps.payments.services import (
    latest_payment,
    mark_payment_failed,
    mark_payment_success,
    start_cod_payment,
    start_fake_online_payment,
)


@login_required
def checkout_payment_view(request, order_number: str):
    """
    - GET: نمایش صفحه انتخاب روش پرداخت
    - POST: خواندن request.POST['method'] در {'cod','online'} و شروع flow
    """
    order = get_object_or_404(Order, number=order_number, user=request.user)

    if order.status != Order.Status.AWAITING_PAYMENT:
        messages.info(request, "This order is not awaiting payment.")
        return redirect("orders:detail", number=order.number)

    if request.method == "POST":
        method = (request.POST.get("method") or "").strip().lower()
        if method not in {"cod", "online"}:
            messages.error(request, "Select a valid payment method.")
            # FIX: route name must be 'checkout' (matches urls.py)
            return redirect("payments:checkout", order_number=order.number)

        if method == "cod":
            start_cod_payment(order)
            messages.success(request, "Order marked as paid (Cash on Delivery).")
            return redirect("payments:success", order_number=order.number)

        # method == "online"
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
    # اگر خطایی بود، تابع بالا ValueError می‌دهد؛ در غیر این صورت payment داریم
    return render(request, "payments/payment_success.html", {"order": order, "payment": payment})


@login_required
def payment_failed_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = mark_payment_failed(order)
    return render(request, "payments/payment_failed.html", {"order": order, "payment": payment})
