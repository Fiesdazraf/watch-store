from django import forms


class DashboardFilterForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All"),
            ("pending", "pending"),
            ("paid", "paid"),
            ("canceled", "canceled"),
            ("shipped", "shipped"),
            ("completed", "completed"),
        ],
    )
