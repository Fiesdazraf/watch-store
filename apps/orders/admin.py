# apps/orders/admin.py
from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet

# IMPORTANT: use Payment from apps.payments
from apps.payments.models import Payment

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    ShippingMethod,
)


# =============================================================================
# Inlines
# =============================================================================
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "variant", "quantity", "unit_price", "subtotal")
    readonly_fields = ("subtotal",)
    autocomplete_fields = ("product", "variant")
    show_change_link = True

    @admin.display(description="Subtotal")
    def subtotal(self, obj: CartItem):
        return obj.subtotal()


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        "product",
        "product_name",
        "sku",
        "variant",
        "unit_price",
        "quantity",
        "total_price",
    )
    readonly_fields = ("total_price",)
    autocomplete_fields = ("product", "variant")
    show_change_link = True

    @admin.display(description="Total")
    def total_price(self, obj: OrderItem):
        return obj.total_price


class PaymentInline(admin.StackedInline):
    """
    One-to-one inline for payments.Payment on Order admin.
    """

    model = Payment  # from apps.payments
    fk_name = "order"
    extra = 0
    can_delete = False
    fields = (
        "method",
        "amount",
        "status",
        "transaction_id",
        "created_at",
    )
    readonly_fields = ("created_at",)


# =============================================================================
# Cart
# =============================================================================
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

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), use_distinct


# =============================================================================
# Order
# =============================================================================
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
    )
    list_select_related = (
        "customer",
        "customer__user",
        "shipping_address",
        "shipping_method",
    )
    inlines = [OrderItemInline, PaymentInline]
    autocomplete_fields = ("customer", "shipping_address", "shipping_method")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "customer",
            "customer__user",
            "shipping_address",
            "shipping_method",
        ).prefetch_related("items")

    @admin.display(description="Customer Email")
    def customer_email(self, obj: Order):
        u = getattr(obj.customer, "user", None)
        return getattr(u, "email", "-")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalc_totals(save=True)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), use_distinct

    # --- Bulk actions
    actions = ["mark_paid", "mark_shipped", "mark_canceled"]

    @admin.action(description="Mark selected orders as Paid")
    def mark_paid(self, request, queryset: QuerySet[Order]):
        updated = queryset.update(status=OrderStatus.PAID)
        self.message_user(request, f"{updated} order(s) marked as PAID.")

    @admin.action(description="Mark selected orders as Shipped")
    def mark_shipped(self, request, queryset: QuerySet[Order]):
        updated = queryset.update(status=OrderStatus.SHIPPED)
        self.message_user(request, f"{updated} order(s) marked as SHIPPED.")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_canceled(self, request, queryset: QuerySet[Order]):
        updated = queryset.update(status=OrderStatus.CANCELED)
        self.message_user(request, f"{updated} order(s) marked as CANCELED.")


# =============================================================================
# ShippingMethod
# =============================================================================
@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "base_price",
        "is_active",
        "est_days_min",
        "est_days_max",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "code")
