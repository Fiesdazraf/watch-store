# apps/accounts/forms.py
import re

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import FieldDoesNotExist, ValidationError

from .models import Address


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _address_owner_filter(qs, *, user):
    """
    Filter an Address queryset by current owner, regardless of whether Address
    uses `user` FK or `customer` FK.
    """
    AddressModel = Address
    # Prefer direct user FK if present
    if _model_has_field(AddressModel, "user"):
        return qs.filter(user=user)
    # Fallback to customer FK if present
    if _model_has_field(AddressModel, "customer"):
        Customer = apps.get_model("customers", "Customer")
        customer = Customer.objects.filter(user=user).first() if user else None
        return qs.filter(customer=customer) if customer else Address.objects.none()
    # If neither field exists, return none (shouldn't happen)
    return Address.objects.none()


def _address_owner_kwargs(*, user) -> dict:
    """
    Build kwargs for creating/assigning the owner field on Address instance.
    """
    AddressModel = Address
    if _model_has_field(AddressModel, "user"):
        return {"user": user}
    if _model_has_field(AddressModel, "customer"):
        Customer = apps.get_model("customers", "Customer")
        customer = Customer.objects.filter(user=user).first() if user else None
        return {"customer": customer} if customer else {}
    return {}


User = get_user_model()

PHONE_REGEX = re.compile(r"^[0-9+\-()\s]{6,}$")


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "At least 8 characters"}
        ),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "Repeat password"}
        ),
    )

    class Meta:
        model = User
        fields = ["email", "full_name", "phone_number"]
        widgets = {
            "email": forms.EmailInput(
                attrs={"autocomplete": "email", "placeholder": "you@example.com"}
            ),
            "full_name": forms.TextInput(attrs={"placeholder": "Your full name"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "+98 912 000 0000"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords don't match.")

        try:
            temp_user = User(
                email=cleaned.get("email"),
                full_name=cleaned.get("full_name"),
            )
            password_validation.validate_password(p1, user=temp_user)
        except ValidationError as e:
            self.add_error("password1", e)

        phone = cleaned.get("phone_number")
        if phone and not PHONE_REGEX.match(phone):
            self.add_error("phone_number", "Enter a valid phone number.")

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.strip().lower()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone_number"]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Your full name"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "+98 912 000 0000"}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data.get("phone_number")
        if phone and not PHONE_REGEX.match(phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone


class AddressForm(forms.ModelForm):
    """
    Address form that:
      - Validates phone format
      - Enforces only one default address per owner (user/customer)
      - Is owner-agnostic (works whether Address has `user` or `customer` FK)
    """

    def __init__(self, *args, **kwargs):
        # Expect the view to pass user=request.user so we can validate default-uniqueness
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Mild UX improvements
        self.fields.get("full_name", forms.Field()).widget.attrs.update(
            {"placeholder": "Receiver full name"}
        )
        self.fields.get("phone_number", forms.Field()).widget.attrs.update(
            {"placeholder": "+98 912 000 0000"}
        )
        self.fields.get("line1", forms.Field()).widget.attrs.update(
            {"placeholder": "Street address, P.O. box, company name"}
        )
        self.fields.get("line2", forms.Field()).widget.attrs.update(
            {"placeholder": "Apartment, suite, unit, building, floor (optional)"}
        )
        self.fields.get("city", forms.Field()).widget.attrs.update({"placeholder": "City"})
        self.fields.get("province", forms.Field()).widget.attrs.update(
            {"placeholder": "State / Province"}
        )
        self.fields.get("postal_code", forms.Field()).widget.attrs.update(
            {"placeholder": "Postal code"}
        )
        self.fields.get("country", forms.Field()).widget.attrs.update({"placeholder": "Country"})

    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone_number",
            "line1",
            "line2",
            "city",
            "province",
            "postal_code",
            "country",
            "is_default",
        ]

    def clean(self):
        cleaned = super().clean()

        phone = cleaned.get("phone_number")
        if phone and not PHONE_REGEX.match(phone):
            self.add_error("phone_number", "Enter a valid phone number.")

        # Enforce only one default address per owner (and per address_type if present)
        if cleaned.get("is_default") and self.user:
            qs = _address_owner_filter(Address.objects.all(), user=self.user)
            qs = qs.filter(is_default=True)

            # If you support address_type, also scope uniqueness by it
            addr_type = cleaned.get("address_type") or getattr(self.instance, "address_type", None)
            if addr_type and Address._meta.get_fields():
                # Only filter if this field exists on model
                if _model_has_field(Address, "address_type"):
                    qs = qs.filter(address_type=addr_type)

            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError("Only one default address per type is allowed.")

        return cleaned

    def save(self, commit=True):
        """
        Ensure the new Address gets the correct owner (user/customer) if not already set.
        """
        instance = super().save(commit=False)
        if self.user:
            # Assign owner only if it's not already set
            if _model_has_field(Address, "user") and getattr(instance, "user_id", None) is None:
                instance.user = self.user
            elif (
                _model_has_field(Address, "customer")
                and getattr(instance, "customer_id", None) is None
            ):
                Customer = apps.get_model("customers", "Customer")
                customer = Customer.objects.filter(user=self.user).first()
                if customer:
                    instance.customer = customer

        if commit:
            instance.save()
        return instance
