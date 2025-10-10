# apps/orders/forms.py
from django import forms

from apps.customers.models import Address

from .models import Order, ShippingMethod


class BulmaMixin:
    """Mixin to apply Bulma CSS classes to form widgets automatically."""

    def _apply_bulma(self):
        for _, field in self.fields.items():
            widget = field.widget
            classes = widget.attrs.get("class", "")
            if isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput)):
                widget.attrs["class"] = f"{classes} input".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"{classes} textarea".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{classes} select is-fullwidth".strip()
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{classes}".strip()  # Bulma برای checkbox خودش label داره


class CheckoutForm(BulmaMixin, forms.Form):
    """Checkout form for logged-in users."""

    address = forms.ModelChoiceField(
        queryset=Address.objects.none(),
        required=False,
        label="Shipping address",
        widget=forms.Select,
    )
    shipping_method = forms.ModelChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        required=True,
        label="Shipping method",
        widget=forms.Select,
    )
    payment_method = forms.ChoiceField(
        choices=list(Order._meta.get_field("payment_method").choices) + [("fake", "Fake Gateway")],
        required=True,
        label="Payment method",
        widget=forms.Select,
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._apply_bulma()

        if user and user.is_authenticated:
            self.fields["address"].queryset = user.addresses.all()
        else:
            self.fields.pop("address", None)  # اگر مهمان بود اصلاً address نداشته باشه
