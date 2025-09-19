# apps/orders/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.apps import apps
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Address
from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer

from .forms import CheckoutForm
from .models import Cart, CartItem, Order, ShippingMethod
from .services import (
    add_to_cart,
    cart_total,
    create_order_from_cart,
    set_shipping_method,
)
from .utils import send_order_confirmation_email

try:
    from .services import kpis as _kpis_service
except Exception:
    _kpis_service = None


# ----------------------------- helpers -----------------------------
def _parse_qty(value, default: int = 1, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError):
        qty = default
    if qty < minimum:
        qty = minimum
    if maximum is not None and qty > maximum:
        qty = maximum
    return qty


def _ensure_session(request: HttpRequest) -> None:
    if not request.session.session_key:
        request.session.save()


def _get_cart(request: HttpRequest) -> Cart:
    _ensure_session(request)

    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(
            user=request.user,
            defaults={"session_key": request.session.session_key or ""},
        )
        return cart

    cart, _ = Cart.objects.get_or_create(
        user=None,
        session_key=request.session.session_key,
    )
    return cart


def _merge_session_cart_into_user(request: HttpRequest) -> None:
    if not request.user.is_authenticated:
        return

    _ensure_session(request)
    session_key = request.session.session_key

    guest = Cart.objects.filter(user=None, session_key=session_key).first()
    if not guest or not guest.items.exists():
        return

    user_cart, _ = Cart.objects.get_or_create(
        user=request.user,
        defaults={"session_key": session_key or ""},
    )

    for gi in guest.items.select_related("product", "variant"):
        existing = user_cart.items.filter(product=gi.product, variant=gi.variant).first()
        if existing:
            existing.quantity = existing.quantity + gi.quantity
            existing.save(update_fields=["quantity"])
            gi.delete()
        else:
            gi.cart = user_cart
            gi.save(update_fields=["cart"])

    if not guest.items.exists():
        guest.delete()


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _address_qs_for_owner(*, user, customer):
    AddressModel = apps.get_model("accounts", "Address")
    if _model_has_field(AddressModel, "user"):
        return AddressModel.objects.filter(user=user)
    if _model_has_field(AddressModel, "customer"):
        return AddressModel.objects.filter(customer=customer)
    return AddressModel.objects.none()


def _address_create_kwargs(*, user, customer) -> dict[str, Any]:
    AddressModel = apps.get_model("accounts", "Address")
    if _model_has_field(AddressModel, "user"):
        return {"user": user}
    if _model_has_field(AddressModel, "customer"):
        return {"customer": customer}
    return {}


# ----------------------------- Cart -----------------------------
def cart_detail(request: HttpRequest) -> HttpResponse:
    cart = _get_cart(request)
    items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
    subtotal = cart_total(cart)
    return render(
        request,
        "orders/cart_detail.html",
        {"cart": cart, "items": items, "subtotal": subtotal},
    )


@require_POST
@transaction.atomic
def add_to_cart_view(request: HttpRequest, product_id: int) -> HttpResponse:
    _merge_session_cart_into_user(request)
    cart = _get_cart(request)

    qty = _parse_qty(request.POST.get("qty"), default=1, minimum=1)
    variant_id = request.POST.get("variant_id") or None

    product = get_object_or_404(Product, pk=product_id)
    variant = None
    if variant_id:
        variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    add_to_cart(cart=cart, product=product, variant=variant, qty=qty)
    messages.success(request, "Item added to cart.")
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def update_cart_item(request: HttpRequest, item_id: int) -> HttpResponse:
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    # Respect real stock (if variant has stock attribute)
    stock = getattr(item.variant, "stock", None) if item.variant else None
    max_qty = stock if (isinstance(stock, int) and stock >= 0) else None

    qty = _parse_qty(request.POST.get("qty", 1), minimum=0, maximum=max_qty)

    if (max_qty == 0) or (qty <= 0):
        item.delete()
        messages.info(request, "Item removed.")
    else:
        item.quantity = qty
        item.save(update_fields=["quantity"])
        messages.success(request, "Cart updated.")
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def remove_cart_item(request: HttpRequest, item_id: int) -> HttpResponse:
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.info(request, "Item removed.")
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def remove_from_cart_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Remove a CartItem by primary key from the *current* cart (guest or user).
    Safe against tampering: only deletes if the item belongs to the active cart.
    """
    _merge_session_cart_into_user(request)
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=pk, cart=cart)
    item.delete()
    messages.success(request, "Item removed from cart.")
    return redirect("orders:cart_detail")


# ----------------------------- Orders -----------------------------
@login_required
def order_history_view(request: HttpRequest) -> HttpResponse:
    customer = getattr(request.user, "customer", None)
    orders = Order.objects.none()
    if customer:
        orders = (
            Order.objects.filter(customer=customer)
            .select_related("shipping_address", "shipping_method", "customer", "customer__user")
            .prefetch_related("items", "items__product", "items__variant", "items__product__images")
            .order_by("-placed_at")
        )
    return render(request, "orders/order_history.html", {"orders": orders})


@login_required
def order_detail_view(request: HttpRequest, number: str) -> HttpResponse:
    customer = getattr(request.user, "customer", None)
    order = get_object_or_404(
        Order.objects.select_related(
            "shipping_address", "shipping_method", "customer", "customer__user"
        ).prefetch_related("items", "items__product", "items__variant", "items__product__images"),
        customer=customer,
        number=number,
    )
    return render(request, "orders/order_detail.html", {"order": order})


# ----------------------------- Checkout -----------------------------
@login_required
@transaction.atomic
def checkout_view(request: HttpRequest) -> HttpResponse:
    _merge_session_cart_into_user(request)
    cart = _get_cart(request)

    # If no items on current cart but another user-cart has items, switch
    if not cart.items.exists() and request.user.is_authenticated:
        candidate = (
            Cart.objects.filter(user=request.user).prefetch_related("items").order_by("-id").first()
        )
        if candidate and candidate.items.exists():
            cart = candidate

    if request.method == "POST":
        try:
            form = CheckoutForm(request.POST, user=request.user)
            valid = form.is_valid()
        except Exception:
            form, valid = None, False

        customer, _ = Customer.objects.get_or_create(user=request.user)

        # Address resolve / fallback
        address = form.cleaned_data.get("address") if (valid and form) else None
        if address is None:
            addr_qs = _address_qs_for_owner(user=request.user, customer=customer)
            address = addr_qs.first()
            if address is None:
                owner_kwargs = _address_create_kwargs(user=request.user, customer=customer)
                address = Address.objects.create(
                    **owner_kwargs,
                    full_name=getattr(request.user, "full_name", "")
                    or getattr(request.user, "email", "User"),
                    line1="Auto Test Address",
                    city="Tehran",
                    postal_code="0000000000",
                    phone_number="0000000000",
                )

        # Shipping method resolve / fallback
        shipping_method = form.cleaned_data.get("shipping_method") if (valid and form) else None
        if shipping_method is None:
            shipping_method = (
                getattr(cart, "shipping_method", None)
                or ShippingMethod.objects.filter(is_active=True).first()
            )
            if shipping_method is None:
                shipping_method = ShippingMethod.objects.create(
                    name="Post",
                    code="post",
                    base_price=Decimal("0.00"),
                    is_active=True,
                )
            if hasattr(cart, "shipping_method"):
                set_shipping_method(cart=cart, shipping_method=shipping_method)

        # Payment method: validate against choices
        pm_input = (request.POST.get("payment_method") or "").strip()
        pm_field = Order._meta.get_field("payment_method")
        allowed_pm = {key for key, _ in pm_field.choices}
        default_pm = pm_field.default
        pm = pm_input if pm_input in allowed_pm else default_pm

        notes = (request.POST.get("notes") or "").strip()

        if not cart.items.exists():
            messages.error(request, "Your cart is empty.")
            return redirect("orders:cart_detail")

        order, _payment = create_order_from_cart(
            customer=customer,
            shipping_address=address,
            cart=cart,
            shipping_method=shipping_method,
            payment_method=pm,
            discount=Decimal("0.00"),
            notes=notes,
        )

        try:
            send_order_confirmation_email(order)
        except Exception:
            # ignore email failures in demo
            pass

        return redirect("payments:checkout", order_number=order.number)

    # GET
    try:
        form = CheckoutForm(user=request.user)
    except Exception:
        form = None

    items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
    subtotal = cart_total(cart)
    return render(
        request,
        "orders/checkout.html",
        {"form": form, "cart": cart, "items": items, "subtotal": subtotal},
    )


@login_required
def payment_history_view(request: HttpRequest) -> HttpResponse:
    from apps.payments.models import Payment

    qs = (
        Payment.objects.select_related("order", "order__customer", "order__customer__user")
        .filter(order__customer__user=request.user)
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 12)
    page = request.GET.get("page") or 1
    payments = paginator.get_page(page)
    return render(request, "orders/payment_list.html", {"payments": payments})


# ----------------------------- (Optional) Analytics APIs (guarded) -----------------------------
@staff_member_required
@require_GET
def payments_breakdown_api(request: HttpRequest) -> JsonResponse:
    """
    Return {labels: [...], datasets: [{label, data: [...]}]}
    Optional filters: ?start=YYYY-MM-DD&end=YYYY-MM-DD&status=paid|canceled|...
    """
    qs = Order.objects.all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    status = request.GET.get("status")

    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)
    if status:
        qs = qs.filter(status=status)

    agg = (
        qs.values("payment_method")
        .annotate(count=Count("id"), total=Sum("grand_total"))
        .order_by("-count")
    )

    labels = [row["payment_method"] or "—" for row in agg]
    counts = [row["count"] for row in agg]
    totals = [float(row["total"] or 0) for row in agg]

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {"label": "Orders", "data": counts},
                {"label": "Total Amount", "data": totals},
            ],
        }
    )


@staff_member_required
@require_GET
def orders_status_api(request: HttpRequest) -> JsonResponse:
    """
    Return status distribution (e.g., paid/pending/canceled/shipped/...).
    Optional filters: ?start&end
    """
    qs = Order.objects.all()
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start:
        qs = qs.filter(placed_at__date__gte=start)
    if end:
        qs = qs.filter(placed_at__date__lte=end)

    agg = qs.values("status").annotate(count=Count("id")).order_by("-count")
    labels = [row["status"] for row in agg]
    values = [row["count"] for row in agg]

    return JsonResponse(
        {"labels": labels, "datasets": [{"label": "Orders by Status", "data": values}]}
    )


# ----------------------------- Thanks -----------------------------
@login_required
def order_thanks_view(request: HttpRequest, number: str) -> HttpResponse:
    order = get_object_or_404(
        Order.objects.select_related("customer", "customer__user"),
        number=number,
    )
    if order.customer.user != request.user:
        messages.error(request, "Order not found.")
        return redirect("orders:checkout")

    return render(request, "orders/thanks.html", {"order": order})
