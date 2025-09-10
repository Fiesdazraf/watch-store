# apps/payments/admin.py
from django.contrib import admin

from .models import Payment, PaymentStatus


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "provider",
        "amount",
        "currency",
        "status",
        "attempt_count",
        "external_id",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "provider", "currency", "created_at")
    search_fields = ("order__number", "external_id")
    readonly_fields = ("paid_at", "created_at", "updated_at", "attempt_count", "external_id")
    autocomplete_fields = ("order",)

    actions = [
        "mark_as_succeeded",
        "mark_as_failed",
        "mark_as_canceled",
        "mark_as_processing",
        "mark_as_pending",
    ]

    @admin.action(description="Mark selected as SUCCEEDED")
    def mark_as_succeeded(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.SUCCEEDED)
        self.message_user(request, f"{updated} payment(s) marked as SUCCEEDED.")

    @admin.action(description="Mark selected as FAILED")
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.FAILED)
        self.message_user(request, f"{updated} payment(s) marked as FAILED.")

    @admin.action(description="Mark selected as CANCELED")
    def mark_as_canceled(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.CANCELED)
        self.message_user(request, f"{updated} payment(s) marked as CANCELED.")

    @admin.action(description="Mark selected as PROCESSING")
    def mark_as_processing(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.PROCESSING)
        self.message_user(request, f"{updated} payment(s) marked as PROCESSING.")

    @admin.action(description="Mark selected as PENDING")
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.PENDING)
        self.message_user(request, f"{updated} payment(s) marked as PENDING.")
