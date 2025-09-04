# apps/customers/models.py
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


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
