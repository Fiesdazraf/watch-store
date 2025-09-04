# apps/customers/admin.py
from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "newsletter_opt_in", "created_at")
    search_fields = ("user__email", "user__full_name", "phone")
    list_filter = ("newsletter_opt_in",)
