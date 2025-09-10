# apps/orders/forms.py
from __future__ import annotations

from django import forms
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist

from .models import ShippingMethod


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _address_qs_for_owner(*, user):
    """
    Return Address queryset for current owner, regardless of schema:
    - If Address has `user` FK -> filter(user=user)
    - Else if Address has `customer` FK -> filter(customer=<Customer(user=user)>)
    - Else -> none()
    """
    Address = apps.get_model("accounts", "Address")

    # Determine owner field & value dynamically
    if _model_has_field(Address, "user"):
        owner_field = "user"
        owner_value = user
    elif _model_has_field(Address, "customer"):
        Customer = apps.get_model("customers", "Customer")
        owner_field = "customer"
        owner_value = Customer.objects.filter(user=user).first() if user else None
    else:
        return Address.objects.none()

    if owner_value is None:
        return Address.objects.none()

    # Dynamic kwargs avoids any hard-coded 'user=' usage
    return Address.objects.filter(**{owner_field: owner_value})


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(queryset=None, required=True)
    shipping_method = forms.ModelChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        required=False,
        empty_label=None,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["address"].queryset = _address_qs_for_owner(user=user)
        self.fields["address"].empty_label = None
