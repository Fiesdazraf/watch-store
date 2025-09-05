from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
    OrderStatus,
    Payment,
    PaymentMethod,
    add_to_cart,
)
from .services import create_order_from_cart


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
                        # keep latest snapshot policy simple
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
    POST: create order from cart -> redirect to gateway or thank you
    """
    cart = _get_cart(request)

    if request.method == "POST":
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            address = form.cleaned_data["address"]
            shipping_method = form.cleaned_data["shipping_method"]
            payment_method = form.cleaned_data["payment_method"]
            notes = form.cleaned_data.get("notes", "")

            try:
                customer = Customer.objects.get(user=request.user)
            except Customer.DoesNotExist:
                messages.error(request, "Customer profile not found. Please contact support.")
                return redirect("orders:checkout")

            try:
                order, payment = create_order_from_cart(
                    customer=customer,
                    shipping_address=address,
                    cart=cart,
                    shipping_method=shipping_method,
                    payment_method=payment_method,
                    discount=Decimal("0.00"),
                )
                if notes:
                    order.notes = notes
                    order.save(update_fields=["notes"])
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("orders:checkout")

            # COD -> no external gateway; show thanks
            if payment_method == PaymentMethod.COD:
                messages.success(request, "Order placed with Cash on Delivery.")
                return redirect("orders:thanks", number=order.number)

            # Otherwise redirect to a fake/local gateway (demo)
            qs = urlencode(
                {
                    "order": order.number,
                    "amount": str(order.grand_total),
                    "return_url": request.build_absolute_uri("/orders/payment/return/"),
                }
            )
            return redirect(f"{request.build_absolute_uri('/orders/payment/fake/')}?{qs}")
    else:
        form = CheckoutForm(user=request.user)

    cart_items = cart.items.select_related("product", "variant")
    subtotal = cart.get_subtotal()

    ctx = {"form": form, "cart": cart, "items": cart_items, "subtotal": subtotal}
    return render(request, "orders/checkout.html", ctx)


@login_required
def payment_fake_gateway_view(request: HttpRequest) -> HttpResponse:
    """
    Local 'fake' gateway with three buttons: success / failed / cancel.
    Only for demo/portfolio purposes.
    """
    order_number = request.GET.get("order")
    amount = request.GET.get("amount") or "0.00"
    return_url = request.GET.get("return_url")

    if not (order_number and return_url):
        messages.error(request, "Invalid gateway request.")
        return redirect("orders:checkout")

    ctx = {"order_number": order_number, "amount": amount, "return_url": return_url}
    return render(request, "orders/payment_fake.html", ctx)


@login_required
def payment_return_view(request: HttpRequest) -> HttpResponse:
    """
    Handle the payment return from gateway.
    Expects ?order=<number>&status=ok|fail|cancel
    """
    number = request.GET.get("order")
    status = request.GET.get("status")

    if not number:
        messages.error(request, "Missing order number.")
        return redirect("orders:checkout")

    order = get_object_or_404(Order.objects.select_related("payment"), number=number)

    # Ensure the order belongs to the current user
    if order.customer.user != request.user:
        messages.error(request, "Order not found.")
        return redirect("orders:checkout")

    payment: Payment | None = getattr(order, "payment", None)

    if status == "ok":
        if payment:
            if not payment.transaction_id:
                payment.transaction_id = f"DEMO-{payment.pk:08d}"
            payment.mark_success(transaction_id=payment.transaction_id)
        else:
            # Rare case (e.g., switched to COD)
            order.status = OrderStatus.PAID
            order.save(update_fields=["status"])
        messages.success(request, "Payment successful. Thank you!")

    elif status in {"fail", "error"}:
        if payment:
            payment.mark_failed(meta={"reason": "demo-failed"})
        messages.error(request, "Payment failed.")

    elif status == "cancel":
        if payment:
            payment.status = Payment.Status.CANCELED
            payment.save(update_fields=["status"])
        messages.info(request, "Payment canceled.")

    else:
        messages.warning(request, "Unknown payment status.")

    return redirect("orders:thanks", number=order.number)


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
