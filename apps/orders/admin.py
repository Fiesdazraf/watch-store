from django.contrib import admin
from .models import Cart, CartItem

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("session_key", "created_at", "updated_at")
    search_fields = ("session_key",)
    inlines = [CartItemInline]
