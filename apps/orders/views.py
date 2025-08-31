from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from apps.catalog.models import Product, ProductVariant
from .models import Cart, CartItem, add_to_cart

def _get_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key)
    return cart

def cart_detail(request):
    cart = _get_cart(request)
    items = cart.items.select_related("product", "variant", "product__brand")
    return render(request, "orders/cart_detail.html", {"cart": cart, "items": items})

@require_POST
def add_to_cart_view(request, product_id):
    cart = _get_cart(request)
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    variant_id = request.POST.get("variant_id")
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product) if variant_id else None
    qty = int(request.POST.get("qty", 1))
    if qty < 1: qty = 1
    add_to_cart(cart, product, variant, qty)
    messages.success(request, "Added to cart.")
    return redirect("orders:cart_detail")

@require_POST
def update_cart_item(request, item_id):
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    qty = int(request.POST.get("qty", 1))
    if qty <= 0:
        item.delete()
    else:
        item.quantity = qty
        item.save(update_fields=["quantity"])
    return redirect("orders:cart_detail")

@require_POST
def remove_cart_item(request, item_id):
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return redirect("orders:cart_detail")
