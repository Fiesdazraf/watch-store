from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Prefetch
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Order

# Avoid runtime import cycles
if TYPE_CHECKING:
    from apps.payments.models import Payment  # noqa: F401

# If you show product images in cart
from apps.catalog.models import ProductImage

logger = logging.getLogger(__name__)


def _send_templated_email(
    template_base: str,
    context: dict,
    to_email: str,
    from_email: str | None = None,
    reply_to: list[str] | None = None,
) -> None:
    """
    Send email using:
      - `{template_base}_subject.txt`
      - `{template_base}_body.txt`
      - optional `{template_base}_body.html`
    under `templates/emails/`.
    """
    if not to_email:
        logger.info("Skipped sending email: empty recipient for template %s", template_base)
        return

    from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    reply_to = reply_to or []

    # Required templates
    subject = render_to_string(f"emails/{template_base}_subject.txt", context).strip()
    body_txt = render_to_string(f"emails/{template_base}_body.txt", context)

    # Optional HTML body
    try:
        body_html = render_to_string(f"emails/{template_base}_body.html", context)
        # If template exists but empty/whitespace, treat as absent
        if not body_html.strip():
            body_html = None
    except Exception:
        body_html = None

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body_txt,
            from_email=from_email,
            to=[to_email],
            reply_to=reply_to,
        )
        if body_html:
            # Add HTML alternative; text part remains as fallback
            message.attach_alternative(body_html, "text/html")
        else:
            # Ensure plain text is really plain (strip accidental HTML)
            message.body = strip_tags(body_txt)

        message.send(fail_silently=False)
        logger.info("Email sent: %s -> %s", template_base, to_email)
    except Exception as exc:
        # Don't crash the request flow; just log the error
        logger.exception("Email send failed for %s to %s: %s", template_base, to_email, exc)


def send_order_confirmation_email(order: Order) -> None:
    """
    Send order confirmation to the customer.
    """
    user = getattr(order.customer, "user", None)
    to_email = getattr(user, "email", "") or ""
    ctx = {"order": order}
    _send_templated_email(template_base="order_confirmation", context=ctx, to_email=to_email)


def send_payment_receipt_email(order: Order, payment: Payment | None) -> None:
    """
    Send payment receipt after successful payment.
    """
    if payment is None:
        logger.info(
            "Skipped sending payment receipt: payment is None (order #%s)",
            getattr(order, "id", "?"),
        )
        return

    user = getattr(order.customer, "user", None)
    to_email = getattr(user, "email", "") or ""
    ctx = {"order": order, "payment": payment}
    _send_templated_email(template_base="payment_receipt", context=ctx, to_email=to_email)


def get_cart_items_qs(cart):
    """
    Optimized queryset for cart items to avoid N+1 and reduce payload.
    Assumes you show a small image in the cart summary.
    """
    return (
        cart.items.select_related("product", "variant")
        .only(
            "id",
            "quantity",
            "unit_price",
            "product__id",
            "product__slug",
            "product__title",
            "product__price",
            "variant__id",
            "variant__sku",
        )
        .prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.only("id", "image", "product_id").order_by("sort"),
            )
        )
    )
