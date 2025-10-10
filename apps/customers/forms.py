# apps/customers/forms.py
from django import forms

from .models import Address


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
                widget.attrs["class"] = f"{classes}".strip()  # Bulma خودش label داره


class AddressForm(BulmaMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone",
            "line1",
            "line2",
            "city",
            "province",
            "postal_code",
            "country",
        ]
        labels = {
            "full_name": "Full name",
            "phone": "Phone number",
            "line1": "Address line 1",
            "line2": "Address line 2",
            "city": "City",
            "province": "Province / State",
            "postal_code": "Postal code",
            "country": "Country",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bulma()

        # Placeholderها برای UX بهتر
        self.fields["full_name"].widget.attrs["placeholder"] = "John Doe"
        self.fields["phone"].widget.attrs["placeholder"] = "+98..."
        self.fields["line1"].widget.attrs["placeholder"] = "Street address, building"
        self.fields["line2"].widget.attrs["placeholder"] = "Apartment, suite, etc."
        self.fields["city"].widget.attrs["placeholder"] = "City"
        self.fields["province"].widget.attrs["placeholder"] = "Province"
        self.fields["postal_code"].widget.attrs["placeholder"] = "Postal code"
