from django.utils import timezone

from apps.invoices.models import Invoice, InvoiceStatus


def create_invoice_for_order(order):
    """
    Create or return existing invoice for given order.
    Ensures that paid orders have paid_at set and correct status.
    """
    invoice, created = Invoice.objects.get_or_create(
        order=order,
        defaults={
            "amount": order.grand_total,
            "status": InvoiceStatus.PAID if order.status == "paid" else InvoiceStatus.PENDING,
            "issued_at": timezone.now(),
            "paid_at": timezone.now() if order.status == "paid" else None,
        },
    )

    # If invoice already existed but order just got paid now
    if not created and order.status == "paid" and invoice.status != InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at"])

    return invoice
