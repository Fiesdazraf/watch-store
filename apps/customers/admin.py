from django.contrib import admin

from .models import Address, Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "marketing_opt_in", "created_at")
    search_fields = ("user__username", "user__email", "phone")
    list_filter = ("marketing_opt_in", "created_at")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("customer", "full_name", "city", "country", "is_default")
    list_filter = ("country", "is_default")
    search_fields = ("full_name", "city", "postal_code")
