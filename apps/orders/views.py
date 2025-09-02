from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction

from apps.catalog.models import Product, ProductVariant
from .models import Cart, CartItem, add_to_cart, Order


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
                    # keep unit_price snapshot policy simple: prefer latest snapshot from add_to_cart
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
