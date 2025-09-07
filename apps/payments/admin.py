# apps/payments/admin.py
from django.contrib import admin

from .models import Payment, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "amount", "status", "transaction_id", "created_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("order__number", "transaction_id")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("order", "method")

    actions = ["mark_paid", "mark_failed"]

    @admin.action(description="Mark selected as PAID")
    def mark_paid(self, request, queryset):
        updated = queryset.update(status="paid")
        self.message_user(request, f"{updated} payment(s) marked as PAID.")

    @admin.action(description="Mark selected as FAILED")
    def mark_failed(self, request, queryset):
        updated = queryset.update(status="failed")
        self.message_user(request, f"{updated} payment(s) marked as FAILED.")
