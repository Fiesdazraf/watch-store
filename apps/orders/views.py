from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.customers.models import Customer

from .forms import CheckoutForm
from .models import (
    Cart,
    CartItem,
    Order,
    add_to_cart,
)
from .services import create_order_from_cart
from .utils import send_order_confirmation_email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_qty(value, default: int = 1, minimum: int = 1, maximum: int | None = None) -> int:
    """Parse and clamp quantity to a safe integer range."""
    try:
        qty = int(value)
    except (TypeError, ValueError):
        qty = default
    if qty < minimum:
        qty = minimum
    if maximum is not None and qty > maximum:
        qty = maximum
    return qty


def _get_cart(request) -> Cart:
    """
    Return the active cart.
    If user is authenticated, also merge any guest cart by session_key.
    """
    if request.user.is_authenticated:
        user_cart, _ = Cart.objects.get_or_create(user=request.user, session_key="")
        # Merge guest cart (if exists)
        if request.session.session_key:
            guest = (
                Cart.objects.filter(session_key=request.session.session_key, user=None)
                .select_related()
                .prefetch_related("items")
                .first()
            )
            if guest and guest.id != user_cart.id:
                for it in guest.items.all():
                    existing = user_cart.items.filter(
                        product=it.product, variant=it.variant
                    ).first()
                    if existing:
                        existing.quantity += it.quantity
                        existing.save(update_fields=["quantity"])
                    else:
                        it.pk = None
                        it.cart = user_cart
                        it.save()
                guest.delete()
        return user_cart

    # Anonymous cart
    if not request.session.session_key:
        request.session.create()
    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user=None)
    return cart


# ---------------------------------------------------------------------------
# Cart views
# ---------------------------------------------------------------------------
def cart_detail(request: HttpRequest) -> HttpResponse:
    cart = _get_cart(request)
    items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
    subtotal = cart.get_subtotal()
    ctx = {"cart": cart, "items": items, "subtotal": subtotal}
    return render(request, "orders/cart_detail.html", ctx)


@require_POST
@transaction.atomic
def add_to_cart_view(request: HttpRequest, product_id: int) -> HttpResponse:
    cart = _get_cart(request)
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    # Variant handling
    variant = None
    variant_id = request.POST.get("variant_id")
    variants_qs = product.variants.filter(is_active=True)

    if variants_qs.exists():
        if not variant_id:
            messages.error(request, "Please select a variant.")
            return redirect("catalog:product_detail", slug=product.slug)
        variant = get_object_or_404(variants_qs, pk=variant_id)
        if getattr(variant, "stock", 0) <= 0:
            messages.error(request, "Selected variant is out of stock.")
            return redirect("catalog:product_detail", slug=product.slug)

    # Quantity (clamp to stock when variant exists)
    max_qty = max(1, getattr(variant, "stock", 0)) if variant else None
    qty = _parse_qty(request.POST.get("qty", 1), minimum=1, maximum=max_qty)

    add_to_cart(cart, product, variant, qty)
    messages.success(request, "Added to cart.")

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def update_cart_item(request: HttpRequest, item_id: int) -> HttpResponse:
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    # If variant has stock enforcement
    max_qty = max(1, getattr(item.variant, "stock", 0)) if item.variant else None
    qty = _parse_qty(request.POST.get("qty", 1), minimum=0, maximum=max_qty)

    if qty <= 0:
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


# ---------------------------------------------------------------------------
# Orders list / detail
# ---------------------------------------------------------------------------
@login_required
def order_history_view(request: HttpRequest) -> HttpResponse:
    customer = getattr(request.user, "customer", None)
    orders = Order.objects.none()
    if customer:
        orders = (
            Order.objects.filter(customer=customer)
            .select_related("shipping_address", "customer", "customer__user")
            .order_by("-placed_at")
        )
    return render(request, "orders/order_history.html", {"orders": orders})


@login_required
def order_detail_view(request: HttpRequest, number: str) -> HttpResponse:
    customer = getattr(request.user, "customer", None)
    order = get_object_or_404(
        Order.objects.select_related(
            "shipping_address", "customer", "customer__user"
        ).prefetch_related("items"),
        customer=customer,
        number=number,
    )
    return render(request, "orders/order_detail.html", {"order": order})


# ---------------------------------------------------------------------------
# Checkout & payment
# ---------------------------------------------------------------------------
@login_required
def checkout_view(request: HttpRequest) -> HttpResponse:
    """
    GET: render checkout summary + form
    POST: create order from cart -> redirect to payments:checkout_payment
    """
    cart = _get_cart(request)

    if request.method == "POST":
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            address = form.cleaned_data["address"]
            shipping_method = form.cleaned_data["shipping_method"]
            notes = form.cleaned_data.get("notes", "")

            try:
                customer = Customer.objects.get(user=request.user)
            except Customer.DoesNotExist:
                messages.error(request, "Customer profile not found. Please contact support.")
                return redirect("orders:checkout")

            try:
                order, _payment = create_order_from_cart(
                    customer=customer,
                    shipping_address=address,
                    cart=cart,
                    shipping_method=shipping_method,
                    discount=Decimal("0.00"),
                )
                if notes:
                    order.notes = notes
                    order.save(update_fields=["notes"])

                # confirmation email about order creation (not payment)
                send_order_confirmation_email(order)

            except ValueError as e:
                messages.error(request, str(e))
                return redirect("orders:checkout")

            # ✅ New flow: always go to payments app to choose/confirm payment
            return redirect("payments:checkout_payment", order_number=order.number)

    else:
        form = CheckoutForm(user=request.user)

    cart_items = cart.items.select_related("product", "variant")
    subtotal = cart.get_subtotal()
    ctx = {"form": form, "cart": cart, "items": cart_items, "subtotal": subtotal}
    return render(request, "orders/checkout.html", ctx)


@login_required
def payment_history_view(request: HttpRequest) -> HttpResponse:
    """
    Show all payments of the current user (from their orders).
    """
    # Local import to avoid tight coupling
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


@login_required
def order_thanks_view(request: HttpRequest, number: str) -> HttpResponse:
    """
    Simple thank-you page showing order number and short summary.
    """
    order = get_object_or_404(
        Order.objects.select_related("customer", "customer__user"), number=number
    )
    if order.customer.user != request.user:
        messages.error(request, "Order not found.")
        return redirect("orders:checkout")

    return render(request, "orders/thanks.html", {"order": order})
