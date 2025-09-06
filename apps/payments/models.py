from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.Model):
    # e.g. "Online", "Cash on Delivery"
    name = models.CharField(max_length=50)
    # e.g. "online", "cod"
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Payment Method")
        verbose_name_plural = _("Payment Methods")

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment_record",
    )
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    raw_gateway_payload = models.JSONField(blank=True, null=True)  # for audit/mock debug
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")

    def __str__(self) -> str:
        return f"Payment #{self.id} - {self.order.number} - {self.status}"
