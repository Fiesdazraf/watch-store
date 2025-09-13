# apps/orders/admin.py
from __future__ import annotations

from django.contrib import admin
from django.db.models import Q, QuerySet
from django.utils.html import format_html

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
    fields = ("method", "amount", "status", "transaction_id", "created_at")
    readonly_fields = ("created_at",)


# =============================================================================
# Custom Filters (Payment status)
# =============================================================================
class PaymentStateFilter(admin.SimpleListFilter):
    title = "Payment state"
    parameter_name = "payment_state"

    def lookups(self, request, model_admin):
        return [
            ("paid", "Paid"),
            ("unpaid", "Unpaid"),
            ("failed", "Failed"),
            ("haspay", "Has Payment row"),
            ("nopay", "No Payment row"),
        ]

    def queryset(self, request, queryset: QuerySet[Order]):
        # NOTE: adjust the exact values to your Payment.status choices if different
        if self.value() == "paid":
            return queryset.filter(payment__status__iexact="paid")
        if self.value() == "failed":
            return queryset.filter(payment__status__iexact="failed")
        if self.value() == "unpaid":
            # unpaid = has payment but not paid/failed OR has no payment
            return queryset.filter(Q(payment__isnull=True) | ~Q(payment__status__iexact="paid"))
        if self.value() == "haspay":
            return queryset.filter(payment__isnull=False)
        if self.value() == "nopay":
            return queryset.filter(payment__isnull=True)
        return queryset


# =============================================================================
# Cart
# =============================================================================
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "session_key", "subtotal_fmt", "created_at", "updated_at")
    search_fields = ("session_key", "user__email", "user__full_name")
    list_filter = ("created_at", "updated_at")
    list_select_related = ("user",)
    inlines = [CartItemInline]
    ordering = ("-updated_at", "-created_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user").prefetch_related("items")

    @admin.display(description="User")
    def user_email(self, obj):
        return getattr(obj.user, "email", "-")

    @admin.display(description="Subtotal")
    def subtotal_fmt(self, obj):
        return f"{obj.get_subtotal():,.0f}"

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
        "status_badge",
        "payment_method",
        "payment_status_badge",
        "subtotal_fmt",
        "shipping_cost_fmt",
        "discount_total_fmt",
        "grand_total_fmt",
        "placed_at",
    )
    list_display_links = ("number", "customer_email")
    list_filter = ("status", "payment_method", PaymentStateFilter, "placed_at")
    search_fields = (
        "number",
        "customer__user__email",
        "customer__user__full_name",
        "items__sku",
        "items__product_name",
    )
    readonly_fields = ("number", "subtotal", "grand_total", "placed_at", "updated_at")
    list_select_related = ("customer", "customer__user", "shipping_address", "shipping_method")
    inlines = [OrderItemInline, PaymentInline]
    autocomplete_fields = ("customer", "shipping_address", "shipping_method")
    date_hierarchy = "placed_at"
    ordering = ("-placed_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "customer",
            "customer__user",
            "shipping_address",
            "shipping_method",
        ).prefetch_related("items", "payment")

    # --- Display helpers
    @admin.display(description="Customer Email")
    def customer_email(self, obj: Order):
        u = getattr(obj.customer, "user", None)
        return getattr(u, "email", "-")

    @admin.display(description="Status")
    def status_badge(self, obj: Order):
        # رنگ‌های پیشنهادی؛ در صورت تفاوت نام وضعیت‌ها در مدل، این map را تغییر بده
        color_map = {
            getattr(OrderStatus, "PENDING", "PENDING"): "#999",
            getattr(OrderStatus, "PROCESSING", "PROCESSING"): "#2980b9",
            getattr(OrderStatus, "SHIPPED", "SHIPPED"): "#8e44ad",
            getattr(OrderStatus, "DELIVERED", "DELIVERED"): "#27ae60",
            getattr(OrderStatus, "CANCELED", "CANCELED"): "#e74c3c",
            getattr(OrderStatus, "PAID", "PAID"): "#16a085",  # اگر در مدل شما Status=PAID وجود دارد
        }
        val = getattr(obj, "status", "")
        color = color_map.get(val, "#555")
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, val)

    @admin.display(description="Payment Status")
    def payment_status_badge(self, obj: Order):
        pay: Payment | None = getattr(obj, "payment", None)
        if not pay:
            return format_html('<span style="color:#999">—</span>')
        # NOTE: نام وضعیت‌ها را با مدل واقعی هم‌سو کن
        val = getattr(pay, "status", "").lower()
        if val == "paid":
            color = "#27ae60"
        elif val == "failed":
            color = "#e74c3c"
        elif val in {"pending", "processing"}:
            color = "#f39c12"
        else:
            color = "#555"
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, val or "-")

    @admin.display(description="Subtotal")
    def subtotal_fmt(self, obj: Order):
        return f"{getattr(obj, 'subtotal', 0):,.0f}"

    @admin.display(description="Shipping")
    def shipping_cost_fmt(self, obj: Order):
        return f"{getattr(obj, 'shipping_cost', 0):,.0f}"

    @admin.display(description="Discount")
    def discount_total_fmt(self, obj: Order):
        return f"{getattr(obj, 'discount_total', 0):,.0f}"

    @admin.display(description="Grand Total")
    def grand_total_fmt(self, obj: Order):
        return f"{getattr(obj, 'grand_total', 0):,.0f}"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalc_totals(save=True)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), use_distinct

    # --- Bulk actions
    actions = ["mark_paid", "mark_shipped", "mark_canceled", "recalc_totals"]

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

    @admin.action(description="Recalculate totals")
    def recalc_totals(self, request, queryset: QuerySet[Order]):
        count = 0
        for order in queryset:
            order.recalc_totals(save=True)
            count += 1
        self.message_user(request, f"Recalculated totals for {count} order(s).")


# =============================================================================
# ShippingMethod
# =============================================================================
@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "base_price_fmt", "is_active", "est_days_min", "est_days_max")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

    @admin.display(description="Base Price")
    def base_price_fmt(self, obj):
        return f"{getattr(obj, 'base_price', 0):,.0f}"
