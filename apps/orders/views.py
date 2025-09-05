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
from .models import Cart, CartItem, Order, OrderStatus, Payment, PaymentMethod, add_to_cart
from .services import create_order_from_cart


def _parse_qty(value, default=1, minimum=1, maximum=None):
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


def _get_cart(request):
    """
    Return the active cart.
    If user is authenticated, also merge any guest cart by session_key into the user cart.
    """
    if request.user.is_authenticated:
        user_cart, _ = Cart.objects.get_or_create(user=request.user, session_key="")
        # Merge guest cart (if exists)
        if request.session.session_key:
            try:
                guest_cart = (
                    Cart.objects.select_related()
                    .prefetch_related("items")
                    .get(session_key=request.session.session_key, user=None)
                )
            except Cart.DoesNotExist:
                return user_cart

            # Move/merge items
            for it in guest_cart.items.all():
                existing = user_cart.items.filter(product=it.product, variant=it.variant).first()
                if existing:
                    # keep unit_price snapshot policy simple
                    # prefer latest snapshot from add_to_cart
                    existing.quantity += it.quantity
                    existing.save(update_fields=["quantity"])
                else:
                    it.pk = None
                    it.cart = user_cart
                    it.save()

            guest_cart.delete()
        return user_cart
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user=None)
        return cart


def cart_detail(request):
    cart = _get_cart(request)
    items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
    subtotal = cart.get_subtotal()
    return render(
        request,
        "orders/cart_detail.html",
        {"cart": cart, "items": items, "subtotal": subtotal},
    )


@require_POST
@transaction.atomic
def add_to_cart_view(request, product_id):
    cart = _get_cart(request)
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    # Variant handling
    variant = None
    variant_id = request.POST.get("variant_id")
    variants_qs = product.variants.filter(is_active=True)

    if variants_qs.exists():
        # Product has variants -> require one AND require stock
        if not variant_id:
            messages.error(request, "Please select a variant.")
            return redirect("catalog:product_detail", slug=product.slug)
        variant = get_object_or_404(variants_qs, pk=variant_id)
        if variant.stock <= 0:
            messages.error(request, "Selected variant is out of stock.")
            return redirect("catalog:product_detail", slug=product.slug)

    # Quantity with stock clamp (if variant exists -> clamp to its stock)
    if variant:
        qty = _parse_qty(request.POST.get("qty", 1), minimum=1, maximum=max(1, variant.stock))
    else:
        qty = _parse_qty(request.POST.get("qty", 1), minimum=1)

    add_to_cart(cart, product, variant, qty)
    messages.success(request, "Added to cart.")

    # Optional UX: go back to the referring page if available
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def update_cart_item(request, item_id):
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    # If variant exists, enforce stock; else just clamp to >=1
    max_qty = None
    if item.variant:
        max_qty = max(1, item.variant.stock)

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
def remove_cart_item(request, item_id):
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.info(request, "Item removed.")
    return redirect("orders:cart_detail")


@login_required
def order_history_view(request):
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
def order_detail_view(request, number):  # <-- number
    customer = getattr(request.user, "customer", None)
    order = get_object_or_404(
        Order.objects.select_related(
            "shipping_address", "customer", "customer__user"
        ).prefetch_related("items"),
        customer=customer,
        number=number,
    )
    return render(request, "orders/order_detail.html", {"order": order})


def _get_user_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def checkout_view(request: HttpRequest) -> HttpResponse:
    """
    GET: render checkout summary + form
    POST: create order from cart -> redirect to gateway or thank you
    """
    cart = _get_user_cart(request.user)

    if request.method == "POST":
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            address = form.cleaned_data["address"]
            shipping_method = form.cleaned_data["shipping_method"]
            payment_method = form.cleaned_data["payment_method"]
            notes = form.cleaned_data.get("notes", "")

            # Map user -> customer (assuming 1-1)
            customer = Customer.objects.get(user=request.user)

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
            # You can replace this with a real gateway redirect (e.g., Zarinpal/Stripe).
            qs = urlencode(
                {
                    "order": order.number,
                    "amount": str(order.grand_total),
                    "return_url": request.build_absolute_uri(
                        # returns to /payment/return/?order=...&status=ok|fail|cancel
                        # We pass only base; fake view will append status according to user click
                        # For live gateways you won't need this trick.
                        # name must match urls.py
                        # Safer to use absolute URL via build_absolute_uri
                        # If behind a proxy set SECURE_PROXY_SSL_HEADER etc.
                        # Using path here:
                        "/orders/payment/return/"
                    ),
                }
            )
            return redirect(f"{request.build_absolute_uri('/orders/payment/fake/')}?{qs}")

    else:
        form = CheckoutForm(user=request.user)

    # Render summary
    cart_items = cart.items.select_related("product", "variant")
    subtotal = cart.get_subtotal()

    ctx = {
        "form": form,
        "cart": cart,
        "items": cart_items,
        "subtotal": subtotal,
    }
    return render(request, "orders/checkout.html", ctx)


@login_required
def payment_fake_gateway_view(request: HttpRequest) -> HttpResponse:
    """
    A local 'fake' gateway screen with two buttons:
    - Pay Success -> redirect to payment_return with status=ok
    - Pay Failed  -> redirect to payment_return with status=fail
    - Cancel      -> redirect to payment_return with status=cancel
    This is only for portfolio/demo purposes.
    """
    order_number = request.GET.get("order")
    amount = request.GET.get("amount") or "0.00"
    return_url = request.GET.get("return_url")

    if not (order_number and return_url):
        messages.error(request, "Invalid gateway request.")
        return redirect("orders:checkout")

    ctx = {
        "order_number": order_number,
        "amount": amount,
        "return_url": return_url,
    }
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
            # If no transaction_id yet, add demo one
            if not payment.transaction_id:
                payment.transaction_id = f"DEMO-{payment.pk:08d}"
            payment.mark_success(transaction_id=payment.transaction_id)
        else:
            # In rare cases (e.g., switched to COD), still mark order as paid
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
