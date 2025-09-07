from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.payments.models import Payment

from .models import Order


def _send_email(*, subject: str, body: str, to_email: str) -> None:
    """
    Internal helper to send an email using Django's send_mail.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    if not to_email:
        return
    send_mail(subject, body, from_email, [to_email], fail_silently=True)


def send_order_confirmation_email(order: Order) -> None:
    """
    Send order confirmation email to the customer after placing an order.
    """
    user = getattr(order.customer, "user", None)
    to_email = getattr(user, "email", "")
    ctx = {"order": order}
    subject = render_to_string("emails/order_confirmation_subject.txt", ctx).strip()
    body = render_to_string("emails/order_confirmation_body.txt", ctx)
    _send_email(subject=subject, body=body, to_email=to_email)


def send_payment_receipt_email(order: Order, payment: Payment | None) -> None:
    """
    Send a payment receipt email after successful payment.
    """
    if payment is None:
        return
    user = getattr(order.customer, "user", None)
    to_email = getattr(user, "email", "")
    ctx = {"order": order, "payment": payment}
    subject = render_to_string("emails/payment_receipt_subject.txt", ctx).strip()
    body = render_to_string("emails/payment_receipt_body.txt", ctx)
    _send_email(subject=subject, body=body, to_email=to_email)
