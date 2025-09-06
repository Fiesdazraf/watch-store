from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string

from apps.orders.models import Order

from .forms import PaymentMethodForm
from .models import Payment


def checkout_payment_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    if order.status != Order.Status.AWAITING_PAYMENT:
        messages.info(request, "This order is not awaiting payment.")
        return redirect("orders:detail", number=order.number)

    if request.method == "POST":
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data["method"]

            # Ensure a Payment row exists (idempotent)
            payment, _created = Payment.objects.get_or_create(
                order=order,
                defaults={
                    "method": method,
                    "amount": order.total_payable,
                    "status": Payment.Status.PENDING,
                },
            )
            if not _created:
                payment.method = method
                payment.amount = order.total_payable
                payment.status = Payment.Status.PENDING
                payment.save()

            if method.code == "cod":
                # Cash on Delivery shortcut (no gateway)
                with transaction.atomic():
                    order.status = Order.Status.PAID
                    order.save(update_fields=["status"])
                    payment.status = Payment.Status.PAID
                    payment.transaction_id = f"COD-{get_random_string(10)}"
                    payment.save(update_fields=["status", "transaction_id"])
                messages.success(request, "Order marked as paid (Cash on Delivery).")
                return redirect("payments:success", order_number=order.number)

            # Online → go to mock gateway
            return redirect("payments:mock_gateway", order_number=order.number)
    else:
        form = PaymentMethodForm()

    return render(
        request,
        "payments/checkout_payment.html",
        {
            "order": order,
            "form": form,
        },
    )


def mock_gateway_view(request, order_number: str):
    """A dummy page that simulates a hosted payment page with two buttons."""
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = getattr(order, "payment", None)
    if not payment:
        messages.error(request, "No payment session found.")
        return redirect("payments:checkout_payment", order_number=order.number)

    # Show a fake gateway with two options: Success / Fail
    return render(request, "payments/mock_gateway.html", {"order": order, "payment": payment})


def payment_success_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = getattr(order, "payment", None)
    if not payment:
        messages.error(request, "No payment found for this order.")
        return redirect("orders:detail", number=order.number)

    if payment.status != Payment.Status.PAID:
        # Mark paid if coming from mock success
        with transaction.atomic():
            payment.status = Payment.Status.PAID
            if not payment.transaction_id:
                payment.transaction_id = f"MOCK-{get_random_string(12)}"
            payment.save(update_fields=["status", "transaction_id"])
            order.status = Order.Status.PAID
            order.save(update_fields=["status"])

    # TODO: send emails/notifications here
    return render(request, "payments/payment_success.html", {"order": order, "payment": payment})


def payment_failed_view(request, order_number: str):
    order = get_object_or_404(Order, number=order_number, user=request.user)
    payment = getattr(order, "payment", None)
    if not payment:
        messages.error(request, "No payment found for this order.")
        return redirect("orders:detail", number=order.number)

    if payment.status != Payment.Status.FAILED:
        with transaction.atomic():
            payment.status = Payment.Status.FAILED
            payment.transaction_id = f"MOCK-FAIL-{get_random_string(8)}"
            payment.save(update_fields=["status", "transaction_id"])
            # Optional: keep order awaiting payment so user can retry
            # or mark canceled if you prefer:
            # order.status = Order.Status.CANCELED
            # order.save(update_fields=["status"])

    return render(request, "payments/payment_failed.html", {"order": order, "payment": payment})
