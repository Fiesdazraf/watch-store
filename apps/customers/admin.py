from django.contrib import admin
from .models import CustomerProfile, Address

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "created_at")
    search_fields = ("user__username", "phone")

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("customer", "full_name", "city", "country", "is_default")
    list_filter = ("country", "is_default")
    search_fields = ("full_name", "city", "postal_code")
