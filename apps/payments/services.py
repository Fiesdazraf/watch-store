# apps/payments/services.py
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.orders.models import Order

from .models import Payment, PaymentStatus


def shop_currency() -> str:
    return getattr(settings, "SHOP_CURRENCY", "IRR")


def order_amount(order: Order) -> int:
    """Return payable amount as int (IRR). Adjust here if you use Decimal elsewhere."""
    return int(getattr(order, "total_payable", getattr(order, "total_amount", 0)) or 0)


def latest_payment(order: Order) -> Payment | None:
    return order.payments.order_by("-created_at").first()


# --------------------------------------------------------------------
# Compatibility helpers for diverse Order schemas (no Order.Status need)
# --------------------------------------------------------------------
def is_awaiting_payment(order: Order) -> bool:
    """
    True if order is not yet paid (independent of Order.Status enum).

    Priority:
      1) If order has 'is_paid', use it (False => awaiting)
      2) If 'Status' enum exists, check AWAITING_PAYMENT when available
      3) If 'status' field exists (str), treat unpaid-like states as awaiting
      4) Fallback True
    """
    # 1) is_paid (field or property)
    if hasattr(order, "is_paid"):
        try:
            return not bool(order.is_paid)
        except (AttributeError, ValueError, TypeError):
            # attribute exists but value is malformed
            pass

    # 2) Enum if exists
    Status = getattr(Order, "Status", None)
    if Status is not None and hasattr(Status, "AWAITING_PAYMENT"):
        try:
            return order.status == Status.AWAITING_PAYMENT  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    # 3) String status heuristic
    try:
        order._meta.get_field("status")
    except FieldDoesNotExist:
        # No status field → assume awaiting to be safe
        return True
    else:
        val = getattr(order, "status", None)
        if isinstance(val, str):
            s = val.strip().lower()
            return s in {"awaiting_payment", "pending", "unpaid", "new", ""}
        # Unknown type → be safe
        return True

    # 4) default
    return True


def mark_order_paid(order: Order) -> None:
    """
    Mark order as paid without assuming a specific schema.
    Tries:
      - Order.Status.PAID (if enum exists)
      - order.is_paid = True (if assignable)
      - order.status = "paid" (if status field exists)
      - fallback: save() as is
    """
    # Try enum PAID
    Status = getattr(Order, "Status", None)
    if Status is not None and hasattr(Status, "PAID"):
        try:
            order.status = Status.PAID  # type: ignore[attr-defined]
            order.save(update_fields=["status"])
            return
        except (AttributeError, ValueError):
            pass

    # Try boolean is_paid
    if hasattr(order, "is_paid"):
        is_prop = isinstance(getattr(order.__class__, "is_paid", None), property)
        if not is_prop:
            try:
                order.is_paid = True  # type: ignore[attr-defined]
                order.save(update_fields=["is_paid"])
                return
            except (AttributeError, ValueError, TypeError):
                pass

    # Try string status
    try:
        order._meta.get_field("status")
    except FieldDoesNotExist:
        # Fallback: just save
        order.save()
    else:
        order.status = "paid"  # type: ignore[attr-defined]
        order.save(update_fields=["status"])


# --------------------------------------------------------------------
# Payment flows
# --------------------------------------------------------------------
@transaction.atomic
def start_cod_payment(order: Order) -> Payment:
    """Demo: Cash on Delivery — immediately mark payment succeeded and order paid."""
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
    mark_order_paid(order)
    return payment


def can_retry(order: Order) -> bool:
    p = latest_payment(order)
    if not p:
        return True
    attempts = p.attempt_count or 0
    max_attempts = p.max_attempts or 3
    return p.status in {PaymentStatus.FAILED, PaymentStatus.PENDING} and attempts < max_attempts


@transaction.atomic
def start_fake_online_payment(order: Order) -> tuple[Payment, str]:
    """Demo: Fake gateway — create attempt, set PROCESSING, return mock bank URL."""
    if not can_retry(order):
        raise ValueError("Max retry attempts reached.")

    last = latest_payment(order)
    payment = Payment.objects.create(
        order=order,
        amount=order_amount(order),
        currency=shop_currency(),
        provider="fake",
        status=PaymentStatus.PENDING,
        attempt_count=(last.attempt_count + 1) if last else 1,
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
    """Demo: Mark the latest attempt succeeded and set order to PAID."""
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
    mark_order_paid(order)
    return payment


@transaction.atomic
def mark_payment_failed(
    order: Order, message: str = "User failed the payment on fake gateway."
) -> Payment:
    """Demo: Mark the latest attempt failed. Keep order awaiting so user can retry."""
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
