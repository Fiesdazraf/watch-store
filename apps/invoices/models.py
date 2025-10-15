from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from apps.orders.models import Order


class InvoiceStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    CANCELED = "canceled", "Canceled"


class InvoiceManager(models.Manager):
    def kpis(self):
        total_count = self.count()
        total_amount = self.aggregate(total=Sum("amount"))["total"] or 0
        paid_count = self.filter(status="paid").count()
        paid_ratio = (paid_count / total_count * 100) if total_count else 0
        return {
            "total_invoices": total_count,
            "total_amount": total_amount,
            "paid_ratio": round(paid_ratio, 1),
        }


class Invoice(models.Model):
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    number = models.CharField(max_length=20, unique=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.PENDING
    )
    issued_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Invoice {self.number or self.id} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f"INV-{self.id or ''}{int(timezone.now().timestamp())}"
        super().save(*args, **kwargs)
