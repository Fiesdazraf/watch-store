from django.contrib import admin
from apps.orders.models import Cart, CartItem, Order, OrderItem


# -----------------------------
# Inline for Cart Items
# -----------------------------
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "variant", "quantity", "unit_price", "subtotal")
    readonly_fields = ("subtotal",)

    def subtotal(self, obj):
        return obj.subtotal()


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "subtotal", "created_at", "updated_at")
    search_fields = ("session_key", "user__username", "user__email")
    list_filter = ("created_at", "updated_at")
    inlines = [CartItemInline]

    def subtotal(self, obj):
        return obj.get_subtotal()
    subtotal.short_description = "Subtotal"


# -----------------------------
# Inline for Order Items
# -----------------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "sku", "variant", "unit_price", "quantity", "total_price")
    readonly_fields = ("total_price",)

    def total_price(self, obj):
        return obj.total_price


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "status",
        "payment_method",
        "subtotal",
        "shipping_cost",
        "discount_total",
        "grand_total",
        "placed_at",
    )
    list_filter = ("status", "payment_method", "placed_at")
    search_fields = ("id", "customer__user__username", "customer__user__email")
    readonly_fields = ("subtotal", "grand_total", "placed_at", "updated_at")
    inlines = [OrderItemInline]

    def save_model(self, request, obj, form, change):
        """
        Recalculate totals when saving an order manually in admin.
        """
        obj.recalc_totals(save=False)
        super().save_model(request, obj, form, change)
