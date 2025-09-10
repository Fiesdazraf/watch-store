# apps/payments/services.py
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.orders.models import Order

from .models import Payment, PaymentStatus


def shop_currency() -> str:
    return getattr(settings, "SHOP_CURRENCY", "IRR")


def order_amount(order: Order) -> int:
    # Support both names seen in codebase
    return getattr(order, "total_payable", getattr(order, "total_amount", 0)) or 0


def latest_payment(order: Order) -> Payment | None:
    return order.payments.order_by("-created_at").first()


@transaction.atomic
def start_cod_payment(order: Order) -> Payment:
    """
    Demo: Cash on Delivery — mark payment succeeded and order paid.
    """
    payment = Payment.objects.create(
        order=order,
        amount=order_amount(order),
        currency=shop_currency(),
        provider="cod",
        status=PaymentStatus.SUCCEEDED,
        external_id=f"COD-{get_random_string(10)}",
        attempt_count=0,
        max_attempts=1,
    )
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    return payment


@transaction.atomic
def start_fake_online_payment(order: Order) -> tuple[Payment, str]:
    """
    Demo: Fake gateway — create attempt, set PROCESSING, return mock bank URL.
    """
    payment = Payment.objects.create(
        order=order,
        amount=order_amount(order),
        currency=shop_currency(),
        provider="fake",
        status=PaymentStatus.PENDING,
        attempt_count=0,
        max_attempts=3,
    )
    if not payment.external_id:
        payment.external_id = f"FAKE-{payment.id}"
    payment.status = PaymentStatus.PROCESSING
    payment.save(update_fields=["external_id", "status", "updated_at"])

    bank_url = reverse("payments:mock_gateway", kwargs={"order_number": order.number})
    return payment, bank_url


@transaction.atomic
def mark_payment_success(order: Order) -> Payment:
    """
    Demo: Mark the latest attempt succeeded and set order to PAID.
    """
    payment = latest_payment(order)
    if not payment:
        raise ValueError("No payment to succeed.")
    if payment.status != PaymentStatus.SUCCEEDED:
        payment.status = PaymentStatus.SUCCEEDED
        if not payment.paid_at:
            payment.paid_at = timezone.now()
        if not payment.external_id:
            payment.external_id = f"MOCK-{get_random_string(12)}"
        payment.save(update_fields=["status", "paid_at", "external_id", "updated_at"])

    if order.status != Order.Status.PAID:
        order.status = Order.Status.PAID
        order.save(update_fields=["status"])
    return payment


@transaction.atomic
def mark_payment_failed(
    order: Order, message: str = "User failed the payment on fake gateway."
) -> Payment:
    """
    Demo: Mark the latest attempt failed. Keep order awaiting payment for retry.
    """
    payment = latest_payment(order)
    if not payment:
        raise ValueError("No payment to fail.")
    if payment.status != PaymentStatus.FAILED:
        payment.status = PaymentStatus.FAILED
        payment.last_error = message
        payment.attempt_count = (payment.attempt_count or 0) + 1
        if not payment.external_id:
            payment.external_id = f"MOCK-FAIL-{get_random_string(8)}"
        payment.save(
            update_fields=["status", "last_error", "attempt_count", "external_id", "updated_at"]
        )
    return payment
