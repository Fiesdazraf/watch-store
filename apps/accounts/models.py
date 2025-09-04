from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils import timezone


# -----------------------------
# Custom User
# -----------------------------
class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email.strip().lower())
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)

    email_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # createsuperuser: only email & password

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email or f"User {self.pk}"


# -----------------------------
# Address (names aligned with your forms/templates)
# -----------------------------
class Address(models.Model):
    class AddressType(models.TextChoices):
        SHIPPING = "shipping", "Shipping"
        BILLING = "billing", "Billing"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    address_type = models.CharField(
        max_length=20, choices=AddressType.choices, default=AddressType.SHIPPING
    )

    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(r"^[0-9+\-()\s]{6,}$", message="Enter a valid phone number.")],
    )

    country = models.CharField(max_length=80, default="Iran")
    province = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20, blank=True)

    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)

    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)  # فقط یک‌بار
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "address_type"],
                condition=Q(is_default=True),
                name="unique_default_address_per_type_per_user",
            )
        ]
        ordering = ("-is_default", "-created_at")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(
                user=self.user, address_type=self.address_type, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

    # Aliases to keep older templates safe (optional)
    @property
    def phone(self):
        return self.phone_number

    @property
    def state(self):
        return self.province

    @property
    def address_line_1(self):
        return self.line1

    @property
    def address_line_2(self):
        return self.line2

    def __str__(self):
        return f"{self.get_address_type_display()} - {self.full_name} ({self.city})"
