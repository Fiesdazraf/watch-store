# apps/orders/admin.py
from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
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
    One-to-one inline for Payment on Order admin.
    If you prefer to manage Payment separately, you can remove this inline.
    """

    model = Payment
    extra = 0
    can_delete = False
    fk_name = "order"
    fields = (
        "amount",
        "currency",
        "method",
        "status",
        "gateway_ref",
        "transaction_id",
        "raw_request",
        "raw_response",
        "paid_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "paid_at")


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
        """
        Override default admin search to avoid duplicate rows
        when searching across related fields.
        """
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
        # Prefetch items to speed up admin list and detail
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
        """
        After saving inline items, recalc totals so numbers are always correct.
        """
        super().save_related(request, form, formsets, change)
        form.instance.recalc_totals(save=True)

    def get_search_results(self, request, queryset, search_term):
        """
        Override default search to avoid duplicate rows
        when searching through related fields (items__...).
        """
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
# Payment
# =============================================================================
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "method",
        "status",
        "amount",
        "currency",
        "transaction_id",
        "created_at",
        "paid_at",
    )
    list_filter = ("method", "status", "created_at", "paid_at")
    search_fields = ("order__number", "transaction_id", "gateway_ref")
    readonly_fields = ("created_at", "updated_at", "paid_at")
    autocomplete_fields = ("order",)

    actions = ["set_success", "set_failed", "set_canceled"]

    @admin.action(description="Set status: SUCCESS (and stamp paid_at)")
    def set_success(self, request, queryset: QuerySet[Payment]):
        updated = 0
        for p in queryset.select_related("order"):
            # If you need a dummy transaction id for demo:
            if not p.transaction_id:
                p.transaction_id = f"DEMO-{p.pk:08d}"
            p.mark_success(transaction_id=p.transaction_id)
            updated += 1
        self.message_user(request, f"{updated} payment(s) marked as SUCCESS.")

    @admin.action(description="Set status: FAILED")
    def set_failed(self, request, queryset: QuerySet[Payment]):
        for p in queryset:
            p.mark_failed()
        self.message_user(request, f"{queryset.count()} payment(s) marked as FAILED.")

    @admin.action(description="Set status: CANCELED")
    def set_canceled(self, request, queryset: QuerySet[Payment]):
        updated = queryset.update(status=Payment.Status.CANCELED)
        self.message_user(request, f"{updated} payment(s) marked as CANCELED.")


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
