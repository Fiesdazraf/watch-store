from django.contrib import admin

from .models import Address, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name")  # فقط فیلدهای قطعی
    search_fields = ("email", "full_name")
    ordering = ("email",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "line1", "city", "country", "is_default")
    list_filter = ("country", "is_default")
    search_fields = ("user__email", "line1", "city", "postal_code")
