import re

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from .models import Address

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

    # Normalize & ensure unique email
    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        # If your User.email is unique=True, the DB will enforce; we add a friendly error here too:
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    # Validate password match + strength
    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords don't match.")

        # Run Django's password validators (length, common password, numeric-only, etc.)
        # Provide a minimal user context so validators that depend on user attributes can run.
        try:
            # A temporary user-like object (only email/full_name present)
            temp_user = User(email=cleaned.get("email"), full_name=cleaned.get("full_name"))
            password_validation.validate_password(p1, user=temp_user)
        except ValidationError as e:
            self.add_error("password1", e)

        # Optional: basic phone check (if your model already validates, you can remove this)
        phone = cleaned.get("phone_number")
        if phone and not PHONE_REGEX.match(phone):
            self.add_error("phone_number", "Enter a valid phone number.")

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        # Ensure normalized email persists
        user.email = user.email.strip().lower()
        # Set hashed password
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
    Ensures only one default address per user is kept for your current Address model.
    If later you add `address_type` (shipping/billing), update the filter in clean().
    """

    def __init__(self, *args, **kwargs):
        # Expect the view to pass user=request.user so we can validate uniqueness of default
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Mild UX improvements
        self.fields["full_name"].widget.attrs.update({"placeholder": "Receiver full name"})
        self.fields["phone_number"].widget.attrs.update({"placeholder": "+98 912 000 0000"})
        self.fields["line1"].widget.attrs.update(
            {"placeholder": "Street address, P.O. box, company name"}
        )
        self.fields["line2"].widget.attrs.update(
            {"placeholder": "Apartment, suite, unit, building, floor (optional)"}
        )
        self.fields["city"].widget.attrs.update({"placeholder": "City"})
        self.fields["province"].widget.attrs.update({"placeholder": "State / Province"})
        self.fields["postal_code"].widget.attrs.update({"placeholder": "Postal code"})
        self.fields["country"].widget.attrs.update({"placeholder": "Country"})

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

        # Optional: basic phone validation if model doesn't already enforce
        phone = cleaned.get("phone_number")
        if phone and not PHONE_REGEX.match(phone):
            self.add_error("phone_number", "Enter a valid phone number.")

        # Enforce only one default address per user (and per address_type)
        if cleaned.get("is_default") and self.user:
            qs = Address.objects.filter(user=self.user, is_default=True)
            addr_type = cleaned.get("address_type") or getattr(self.instance, "address_type", None)
            if addr_type:
                qs = qs.filter(address_type=addr_type)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Only one default address per type is allowed.")

        return cleaned
