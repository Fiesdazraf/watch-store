from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q, UniqueConstraint


phone_validator = RegexValidator(
    regex=r"^\+?[0-9\s\-()]{6,20}$",
    message="Enter a valid phone number."
)


class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='customer'
    )
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        full_name = getattr(self.user, "get_full_name", lambda: "")() or ""
        return full_name.strip() or getattr(self.user, "username", str(self.user))


class Address(models.Model):
    customer = models.ForeignKey(
        Customer, related_name='addresses', on_delete=models.CASCADE
    )
    full_name = models.CharField(max_length=120)
    line1 = models.CharField(max_length=180)
    line2 = models.CharField(max_length=180, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(
        max_length=2, default='GB', help_text="ISO 3166-1 alpha-2 (e.g. GB, US, IR)"
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_default', 'id']
        indexes = [
            models.Index(fields=['customer', 'is_default']),
            models.Index(fields=['postal_code']),
        ]
        constraints = [
            # Only one default address per customer
            UniqueConstraint(
                fields=['customer'],
                condition=Q(is_default=True),
                name='uniq_default_address_per_customer'
            )
        ]

    def __str__(self):
        return f"{self.full_name} - {self.line1}, {self.city}"

    def save(self, *args, **kwargs):
        # Normalize fields
        if self.postal_code:
            self.postal_code = self.postal_code.strip().upper()
        if self.country:
            self.country = self.country.strip().upper()

        super().save(*args, **kwargs)

        # Ensure only one default address per customer (app-level enforcement)
        if self.is_default:
            Address.objects.filter(
                customer=self.customer,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
