# apps/payments/models.py
from django.db import models
from django.utils import timezone


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class Payment(models.Model):
    """
    A payment attempt for an order (supports retries).
    Keep one row per attempt so we have a clean history.
    """

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True,
    )
    amount = models.PositiveIntegerField(help_text="Amount in smallest currency unit (e.g., IRR).")
    currency = models.CharField(max_length=10, default="IRR")
    provider = models.CharField(
        max_length=50, default="fake", db_index=True
    )  # e.g., 'fake', 'zarinpal', etc.
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    external_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="External payment/tracking id provided by the gateway.",
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    last_error = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "provider"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Payment #{self.pk} for Order {getattr(self.order, 'number', self.order_id)}"

    # ---- convenience state helpers
    def can_retry(self) -> bool:
        return (
            self.status in {PaymentStatus.FAILED, PaymentStatus.PENDING}
            and self.attempt_count < self.max_attempts
        )

    def mark_processing(self, save=True):
        self.status = PaymentStatus.PROCESSING
        if save:
            self.save(update_fields=["status", "updated_at"])

    def mark_failed(self, message: str = "", save=True):
        self.status = PaymentStatus.FAILED
        self.last_error = message or "Unknown error"
        self.attempt_count = (self.attempt_count or 0) + 1
        if save:
            self.save(update_fields=["status", "last_error", "attempt_count", "updated_at"])

    def mark_succeeded(self, when=None, save=True):
        self.status = PaymentStatus.SUCCEEDED
        self.paid_at = when or timezone.now()
        if save:
            self.save(update_fields=["status", "paid_at", "updated_at"])
