# apps/customers/forms.py
from django import forms

from apps.accounts.models import Address

from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["phone", "date_of_birth", "newsletter_opt_in"]


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "address_type",
            "full_name",
            "phone_number",
            "country",
            "province",
            "city",
            "postal_code",
            "line1",
            "line2",
            "is_default",
            "is_active",
        ]
