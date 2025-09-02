from django.contrib import admin

from apps.orders.models import Cart, CartItem, Order, OrderItem


# -----------------------------
# Inlines
# -----------------------------
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "variant", "quantity", "unit_price", "subtotal")
    readonly_fields = ("subtotal",)
    autocomplete_fields = ("product", "variant")
    show_change_link = True

    def subtotal(self, obj):
        return obj.subtotal()


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "sku", "variant", "unit_price", "quantity", "total_price")
    readonly_fields = ("total_price",)
    autocomplete_fields = ("variant",)
    show_change_link = True

    def total_price(self, obj):
        return obj.total_price


# -----------------------------
# Cart Admin
# -----------------------------
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "session_key", "subtotal", "created_at", "updated_at")
    search_fields = ("session_key", "user__email", "user__full_name")
    list_filter = ("created_at", "updated_at")
    list_select_related = ("user",)
    inlines = [CartItemInline]

    @admin.display(description="User")
    def user_email(self, obj):
        return getattr(obj.user, "email", "-")

    @admin.display(description="Subtotal")
    def subtotal(self, obj):
        return obj.get_subtotal()


# -----------------------------
# Order Admin
# -----------------------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",  # یا اگر number داری: "number",
        "customer_email",
        "status",
        "payment_method",
        "subtotal",
        "shipping_cost",
        "discount_total",
        "grand_total",
        "placed_at",
    )
    list_filter = ("status", "payment_method", "placed_at")
    search_fields = (
        "id",  # اگر number داری: "number",
        "customer__user__email",
        "customer__user__full_name",
        "items__sku",
        "items__product_name",
    )
    readonly_fields = ("subtotal", "grand_total", "placed_at", "updated_at")
    list_select_related = ("customer", "customer__user", "shipping_address")
    inlines = [OrderItemInline]
    autocomplete_fields = ("customer", "shipping_address")

    def save_model(self, request, obj, form, change):
        # اول ذخیره کن تا اگر Order تازه ساخته شده و number/id لازم است، موجود باشد
        super().save_model(request, obj, form, change)
        # بعد از ذخیره، جمع‌ها را دقیق محاسبه و ذخیره کن
        obj.recalc_totals(save=True)

    @admin.display(description="Customer Email")
    def customer_email(self, obj):
        u = getattr(obj.customer, "user", None)
        return getattr(u, "email", "-")

    # اکشن‌های مفید
    actions = ["mark_paid", "mark_shipped", "mark_canceled"]

    @admin.action(description="Mark selected orders as Paid")
    def mark_paid(self, request, queryset):
        updated = queryset.update(status="paid")
        self.message_user(request, f"{updated} order(s) marked as PAID.")

    @admin.action(description="Mark selected orders as Shipped")
    def mark_shipped(self, request, queryset):
        updated = queryset.update(status="shipped")
        self.message_user(request, f"{updated} order(s) marked as SHIPPED.")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_canceled(self, request, queryset):
        updated = queryset.update(status="canceled")
        self.message_user(request, f"{updated} order(s) marked as CANCELED.")
