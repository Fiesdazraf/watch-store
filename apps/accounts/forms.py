# apps/accounts/forms.py
import re

from django import forms
from django.apps import apps
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.core.exceptions import FieldDoesNotExist, ValidationError

from apps.customers.models import Address


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


User = get_user_model()


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "input"}))
    password = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"class": "input"})
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get("email")
        password = self.cleaned_data.get("password")

        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                raise forms.ValidationError("Invalid email or password.")
        return self.cleaned_data

    def get_user(self):
        return getattr(self, "user", None)
