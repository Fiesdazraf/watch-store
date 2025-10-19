# apps/invoices/admin.py
from django.contrib import admin

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "number",
        "amount",
        "status",
        "issued_at",
        "paid_at",
    )
    list_filter = ("status", "issued_at")

    search_fields = ("number", "order__id", "order__user__email")
    date_hierarchy = "issued_at"

    ordering = ("-issued_at",)
