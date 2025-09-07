from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)  # e.g. "online", "cod"
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
        related_name="payment",
    )
    # Option A: direct class reference (recommended)
    method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    # Option B: string reference (alternative)
    # method = models.ForeignKey(
    #     "payments.PaymentMethod",
    #     on_delete=models.PROTECT,
    #     null=True,
    #     blank=True,
    # )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    raw_gateway_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["method"]),
        ]
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")

    def __str__(self) -> str:
        return f"Payment #{self.pk} - {self.order.number} - {self.status}"

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    def mark_paid(self, transaction_id: str | None = None, save: bool = True):
        self.status = self.Status.PAID
        if transaction_id and not self.transaction_id:
            self.transaction_id = transaction_id
        if save:
            self.save(update_fields=["status", "transaction_id"])

    def mark_failed(self, save: bool = True):
        self.status = self.Status.FAILED
        if save:
            self.save(update_fields=["status"])
