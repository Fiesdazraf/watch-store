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
    list_filter = ("status", "method")
    search_fields = ("order__number", "transaction_id")
    readonly_fields = ("created_at",)
