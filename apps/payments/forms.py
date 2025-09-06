from django import forms

from .models import PaymentMethod


class PaymentMethodForm(forms.ModelForm):
    method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
    )
