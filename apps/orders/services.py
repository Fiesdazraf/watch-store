# apps/orders/services.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, TypedDict

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.db import models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.invoices.models import Invoice

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    ShippingMethod,
)

if TYPE_CHECKING:
    from apps.customers.models import Address, Customer
    from apps.payments.models import Payment as PaymentModel

User = get_user_model()


# ----------------------------
# helpers
# ----------------------------
def _to_decimal(value, default: str = "0.00") -> Decimal:
    """
    Safely convert any value to Decimal.
    Handles None, '', 'NaN', Decimal('NaN'), and invalid inputs without raising.
    """
    try:
        # None یا خالی
        if value in (None, "", "None", "null", "NaN"):
            return Decimal(default)

        # اگر خودش Decimal هست، ولی NaN باشه
        if isinstance(value, Decimal):
            if value.is_nan():
                return Decimal(default)
            return value

        # اعداد int و float
        if isinstance(value, (int, float)):
            # اگر float NaN باشه
            if value != value:  # NaN != NaN
                return Decimal(default)
            return Decimal(str(value))

        # رشته‌ها
        s = str(value).strip().replace(",", "")
        if not s or s.lower() in {"none", "null", "nan"}:
            return Decimal(default)
        return Decimal(s)

    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _unit_price_for(product, variant=None) -> Decimal:
    """Always return a valid Decimal('x.xx') with two digits."""

    def safe_decimal(value) -> Decimal:
        try:
            d = Decimal(str(value))
            if d.is_nan() or d.is_infinite():
                return Decimal("0.00")
            return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")

    base = safe_decimal(getattr(product, "price", 0))
    if variant is not None:
        final_price = getattr(variant, "final_price", None)
        if final_price not in (None, "", "None", "null"):
            return safe_decimal(final_price)
        extra = safe_decimal(getattr(variant, "extra_price", 0))
        return safe_decimal(base + extra)
    return base


# ----------------------------
# cart APIs
# ----------------------------
@transaction.atomic
def add_to_cart(*, cart: Cart, product, variant=None, qty: int = 1) -> CartItem:
    """
    Add product or variant to cart safely, compatible with unique constraints and tests.
    """
    qty = int(qty or 1)
    if qty < 1:
        qty = 1

    variant = variant if getattr(variant, "pk", None) else None
    unit_price = _unit_price_for(product, variant)

    # ---------------- FIX for unique constraint and variant mismatch ----------------
    lookup = {"cart": cart}

    if variant:
        lookup["variant"] = variant
        # Use variant.product if exists, fallback to given product
        lookup["product"] = getattr(variant, "product", product)
    else:
        lookup["product"] = product
        lookup["variant__isnull"] = True

    item, created = CartItem.objects.get_or_create(
        defaults={"unit_price": unit_price, "quantity": qty},
        **lookup,
    )
    # -------------------------------------------------------------------------------

    if not created:
        # increase existing quantity safely
        item.quantity = F("quantity") + qty
        item.save(update_fields=["quantity"])
        item.refresh_from_db(fields=["quantity"])

    # sync latest price
    if item.unit_price != unit_price:
        item.unit_price = unit_price
        item.save(update_fields=["unit_price"])

    # ensure at least 1 quantity (edge case)
    if item.quantity == 0:
        item.quantity = qty
        item.save(update_fields=["quantity"])

    # ✅ NEW FIX — always quantize to two decimals
    from decimal import ROUND_HALF_UP, Decimal

    try:
        item.unit_price = Decimal(str(item.unit_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except Exception:
        item.unit_price = Decimal("0.00")
    item.save(update_fields=["unit_price"])

    return item


def set_shipping_method(*, cart: Cart, shipping_method: ShippingMethod | None) -> None:
    """Set shipping method on cart if the field exists."""
    if shipping_method is None:
        return
    if hasattr(cart, "shipping_method"):
        cart.shipping_method = shipping_method
        cart.save(update_fields=["shipping_method"])


def cart_total(cart: Cart) -> Decimal:
    """
    Compute cart total = sum(unit_price * quantity) + shipping_cost.
    Uses ExpressionWrapper to keep DB-side arithmetic typed as Decimal.
    """
    line_total = ExpressionWrapper(
        F("unit_price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    agg = cart.items.aggregate(total=Sum(line_total))
    items_total = _to_decimal(agg["total"] or "0.00")

    sm = getattr(cart, "shipping_method", None)
    shipping_cost = _to_decimal(getattr(sm, "base_price", "0.00")) if sm else Decimal("0.00")
    return items_total + shipping_cost


# ----------------------------
# order creation
# ----------------------------
def _assign_shipping_on_order_kwargs(
    order_kwargs: dict, shipping_method: ShippingMethod | None
) -> Decimal:
    """
    Assign into order_kwargs['shipping_method'] according to Order field type.
    If FK to ShippingMethod → assign instance; else assign shipping code string.
    Returns the base shipping cost.
    """
    if not shipping_method:
        return Decimal("0.00")

    try:
        field = Order._meta.get_field("shipping_method")
    except FieldDoesNotExist:
        return _to_decimal(getattr(shipping_method, "base_price", "0.00"))

    shipping_cost = _to_decimal(getattr(shipping_method, "base_price", "0.00"))
    if (
        isinstance(field, models.ForeignKey)
        and field.remote_field
        and field.remote_field.model == ShippingMethod
    ):
        order_kwargs["shipping_method"] = shipping_method
    else:
        order_kwargs["shipping_method"] = getattr(shipping_method, "code", "") or ""
    return shipping_cost


@transaction.atomic
def create_order_from_cart(
    *,
    customer: Customer,
    shipping_address: Address,
    cart: Cart,
    shipping_method: ShippingMethod | None = None,
    payment_method: str = PaymentMethod.GATEWAY,
    discount: Decimal = Decimal("0.00"),
    notes: str | None = None,
) -> tuple[Order, PaymentModel | None]:
    """
    Create an Order (and items) from a cart snapshot.
    Returns (order, payment) — here payment is None; payments app will create attempts later.
    """
    order_kwargs: dict = {
        "customer": customer,
        "shipping_address": shipping_address,
        "status": OrderStatus.PENDING,
        "payment_method": payment_method,
        "discount_total": _to_decimal(discount),
    }
    if notes:
        order_kwargs["notes"] = notes

    shipping_cost = _assign_shipping_on_order_kwargs(order_kwargs, shipping_method)
    order_kwargs["shipping_cost"] = shipping_cost

    order = Order.objects.create(**order_kwargs)

    # Copy items (bulk_create for performance)
    items_qs = CartItem.objects.select_related("product", "variant").filter(cart=cart)
    order_items = [
        OrderItem(
            order=order,
            product=ci.product,
            variant=ci.variant,
            product_name=getattr(ci.product, "name", "") or str(ci.product),
            sku=(getattr(ci.variant, "sku", "") or getattr(ci.product, "sku", "")),
            unit_price=_to_decimal(ci.unit_price),
            quantity=int(ci.quantity),
        )
        for ci in items_qs
    ]
    if order_items:
        OrderItem.objects.bulk_create(order_items)

    # Totals
    if hasattr(order, "recalc_totals"):
        order.recalc_totals(save=True)
    else:
        items_total = sum(
            (oi.unit_price * oi.quantity for oi in order.items.all()),
            Decimal("0.00"),
        )
        grand = (
            items_total
            + _to_decimal(order_kwargs["shipping_cost"])
            - _to_decimal(order_kwargs["discount_total"])
        )
        if hasattr(order, "subtotal"):
            order.subtotal = items_total
        if hasattr(order, "grand_total"):
            order.grand_total = grand
        order.save()

    # Clear cart
    cart.items.all().delete()

    # payments app will handle actual Payment row
    return order, None


# ---- Analytics helpers -----------------------------------------------------

# IMPORTANT: set this to the real field on Order, otherwise KPIs will be zero.
TOTAL_FIELD = "grand_total"  # adjust if your model uses another name


def _total_annotation():
    # Coalesce to 0, so Sum works even with nulls
    return Coalesce(
        F(TOTAL_FIELD),
        Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )


def _today_range():
    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _week_range():
    now = timezone.now()
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start_of_week, now


def _month_range():
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


# ---- KPIs -----------------------------------------------------------------
class SalesKPIs(TypedDict):
    today: float
    week: float
    month: float


def get_sales_kpis() -> SalesKPIs:
    """
    Sum paid/confirmed orders over today/week/month.
    Adjust statuses to your actual statuses.
    """
    paid_statuses = {OrderStatus.PAID, "completed", "fulfilled"}
    start_today, end_today = _today_range()
    start_week, end_week = _week_range()
    start_month, end_month = _month_range()

    base = Order.objects.filter(status__in=paid_statuses)

    def _sum_between(start, end) -> float:
        agg = base.filter(placed_at__gte=start, placed_at__lte=end).aggregate(
            total=Sum(_total_annotation())
        )
        return float(agg["total"] or 0)

    return {
        "today": _sum_between(start_today, end_today),
        "week": _sum_between(start_week, end_week),
        "month": _sum_between(start_month, end_month),
    }


class OrdersCounters(TypedDict):
    pending: int
    paid: int
    cancelled: int


def get_orders_counters() -> OrdersCounters:
    pending_statuses = {OrderStatus.PENDING, "awaiting_payment"}
    paid_statuses = {OrderStatus.PAID, "completed", "fulfilled"}
    cancelled_statuses = {"cancelled", "refunded"}

    return {
        "pending": Order.objects.filter(status__in=pending_statuses).count(),
        "paid": Order.objects.filter(status__in=paid_statuses).count(),
        "cancelled": Order.objects.filter(status__in=cancelled_statuses).count(),
    }


class UsersCounters(TypedDict):
    new_today: int
    new_month: int


def get_users_counters() -> UsersCounters:
    start_today, end_today = _today_range()
    start_month, end_month = _month_range()

    def _count_between(start, end) -> int:
        # Adjust 'date_joined' if you use another field
        return User.objects.filter(date_joined__gte=start, date_joined__lte=end).count()

    return {
        "new_today": _count_between(start_today, end_today),
        "new_month": _count_between(start_month, end_month),
    }


# ---- Timeseries for charts -------------------------------------------------
class Point(TypedDict):
    label: str
    value: float


def get_sales_timeseries_by_day(start: date, end: date) -> list[Point]:
    """
    Returns daily total invoice amounts between [start, end], inclusive.
    Uses Invoice.issued_at and amount.
    """
    start_dt = timezone.make_aware(datetime.combine(start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end, datetime.max.time()))

    # فقط فاکتورهای پرداخت‌شده را جمع می‌کنیم
    qs = (
        Invoice.objects.filter(
            status="paid",
            issued_at__gte=start_dt,
            issued_at__lte=end_dt,
        )
        .annotate(day=TruncDate("issued_at"))
        .values("day")
        .annotate(total=Sum("amount"))
        .order_by("day")
    )

    # Build full sequence to fill missing days with 0
    data: dict[str, float] = {str(r["day"]): float(r["total"] or 0) for r in qs}

    out: list[Point] = []
    d = start
    while d <= end:
        key = str(d)
        out.append({"label": key, "value": data.get(key, 0.0)})
        d += timedelta(days=1)

    return out


__all__ = [
    "add_to_cart",
    "set_shipping_method",
    "cart_total",
    "create_order_from_cart",
    # analytics
    "get_sales_kpis",
    "get_orders_counters",
    "get_users_counters",
    "get_sales_timeseries_by_day",
]
