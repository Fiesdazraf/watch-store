from __future__ import annotations

from django import forms
from django.conf import settings

from apps.accounts.models import Address

from .models import PaymentMethod, ShippingMethod


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(
        queryset=Address.objects.none(),
        label="Shipping address",
        widget=forms.Select(attrs={"class": "input"}),
    )
    shipping_method = forms.ModelChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        label="Shipping method",
        widget=forms.Select(attrs={"class": "input"}),
    )
    payment_method = forms.ChoiceField(
        choices=PaymentMethod.choices,
        label="Payment method",
        widget=forms.Select(attrs={"class": "input"}),
    )
    notes = forms.CharField(
        label="Notes (optional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "textarea"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit addresses to the current user
        if user and user.is_authenticated:
            self.fields["address"].queryset = Address.objects.filter(user=user)
        # In production you may want to hide FAKE option
        if not settings.DEBUG:
            methods = [m for m in PaymentMethod if m.value != PaymentMethod.FAKE]
            self.fields["payment_method"].choices = [(m.value, m.label) for m in methods]
