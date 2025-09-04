from django.contrib import admin

from apps.orders.models import Cart, CartItem, Order, OrderItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "variant", "quantity", "unit_price", "subtotal")
    readonly_fields = ("subtotal",)
    autocomplete_fields = ("product", "variant")
    show_change_link = True

    @admin.display(description="Subtotal")
    def subtotal(self, obj):
        return obj.subtotal()


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    # ✅ product را اضافه کردیم
    fields = ("product", "product_name", "sku", "variant", "unit_price", "quantity", "total_price")
    readonly_fields = ("total_price",)
    autocomplete_fields = ("product", "variant")  # ✅
    show_change_link = True

    @admin.display(description="Total")
    def total_price(self, obj):
        return obj.total_price


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "session_key", "subtotal", "created_at", "updated_at")
    search_fields = ("session_key", "user__email", "user__full_name")
    list_filter = ("created_at", "updated_at")
    list_select_related = ("user",)
    inlines = [CartItemInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user").prefetch_related("items")

    @admin.display(description="User")
    def user_email(self, obj):
        return getattr(obj.user, "email", "-")

    @admin.display(description="Subtotal")
    def subtotal(self, obj):
        return obj.get_subtotal()


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
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
        "number",
        "customer__user__email",
        "customer__user__full_name",
        "items__sku",
        "items__product_name",
    )
    readonly_fields = (
        "number",
        "subtotal",
        "grand_total",
        "placed_at",
        "updated_at",
    )  # ← number readonly
    list_select_related = ("customer", "customer__user", "shipping_address")
    inlines = [OrderItemInline]
    autocomplete_fields = ("customer", "shipping_address")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("customer", "customer__user", "shipping_address")

    @admin.display(description="Customer Email")
    def customer_email(self, obj):
        u = getattr(obj.customer, "user", None)
        return getattr(u, "email", "-")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalc_totals(save=True)

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
