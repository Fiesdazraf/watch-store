from django.contrib import admin

from .models import Address, Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "newsletter_opt_in", "created_at")
    list_filter = ("newsletter_opt_in",)
    search_fields = ("user__email", "user__full_name", "phone")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "full_name",
        "city",
        "country",
        "default_shipping",
        "default_billing",
        "created_at",
    )
    list_filter = ("country", "default_shipping", "default_billing")
    search_fields = ("full_name", "phone", "line1", "city", "postal_code", "user__email")
