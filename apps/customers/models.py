from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer"
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(r"^[0-9+\-()\s]{6,}$", message="Enter a valid phone number.")],
    )
    date_of_birth = models.DateField(blank=True, null=True)
    newsletter_opt_in = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self):
        return f"{self.user.full_name or self.user.email}"


class Address(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(
        max_length=20,
        validators=[RegexValidator(r"^[0-9+\-()\s]{6,}$", "Enter a valid phone number.")],
    )
    line1 = models.CharField("Address line 1", max_length=255)
    line2 = models.CharField("Address line 2", max_length=255, blank=True)
    city = models.CharField(max_length=100)
    province = models.CharField("State/Province", max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="IR")  # ISO-3166-1 alpha-2

    default_shipping = models.BooleanField(default=False)
    default_billing = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(default_shipping=True),
                name="uniq_default_shipping_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(default_billing=True),
                name="uniq_default_billing_per_user",
            ),
        ]
        ordering = ["-default_shipping", "-default_billing", "-created_at"]

    def save(self, *args, **kwargs):
        # فقط اجازه بده یه آدرس پیش‌فرض برای هر کاربر وجود داشته باشه
        if self.default_shipping:
            Address.objects.filter(user=self.user, default_shipping=True).exclude(
                pk=self.pk
            ).update(default_shipping=False)
        if self.default_billing:
            Address.objects.filter(user=self.user, default_billing=True).exclude(pk=self.pk).update(
                default_billing=False
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} — {self.line1}, {self.city}"
