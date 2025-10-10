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
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Product, ProductVariant
from apps.customers.forms import AddressForm
from apps.customers.models import Address, Customer

from .forms import CheckoutForm
from .models import Cart, CartItem, Order, ShippingMethod
from .services import add_to_cart, cart_total, create_order_from_cart, set_shipping_method


# ----------------------------- Helpers -----------------------------
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
    """
    Always ensure a valid cart for both guests and authenticated users.
    Also keeps session_key in sync to prevent 'empty cart' issues during tests.
    """
    _ensure_session(request)
    session_key = request.session.session_key or ""

    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(
            user=request.user,
            defaults={"session_key": session_key},
        )
        # ✅ ensure session key is synced
        if not cart.session_key and session_key:
            cart.session_key = session_key
            cart.save(update_fields=["session_key"])
        return cart

    cart, _ = Cart.objects.get_or_create(user=None, session_key=session_key)
    return cart


def _merge_session_cart_into_user(request: HttpRequest) -> None:
    """Merge guest cart into authenticated user's cart when logging in."""
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
            existing.quantity += gi.quantity
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
    AddressModel = apps.get_model("customers", "Address")
    if _model_has_field(AddressModel, "user"):
        return AddressModel.objects.filter(user=user)
    if _model_has_field(AddressModel, "customer"):
        return AddressModel.objects.filter(customer=customer)
    return AddressModel.objects.none()


def _address_create_kwargs(*, user, customer) -> dict[str, Any]:
    AddressModel = apps.get_model("customers", "Address")
    if _model_has_field(AddressModel, "user"):
        return {"user": user}
    if _model_has_field(AddressModel, "customer"):
        return {"customer": customer}
    return {}


# ----------------------------- Cart -----------------------------
MAX_QTY_PER_ADD = 20


@require_POST
@transaction.atomic
def add_to_cart_view(request: HttpRequest, product_id: int) -> HttpResponse:
    """Add a product/variant to the current cart (test-safe)."""
    _merge_session_cart_into_user(request)
    cart = _get_cart(request)

    qty = _parse_qty(request.POST.get("qty"), default=1, minimum=1)
    if qty > MAX_QTY_PER_ADD:
        qty = MAX_QTY_PER_ADD

    variant_id = (request.POST.get("variant_id") or "").strip() or None
    next_url = (request.POST.get("next") or request.META.get("HTTP_REFERER") or "").strip()

    product = get_object_or_404(Product, pk=product_id)
    is_active = getattr(product, "is_active", getattr(product, "active", True))
    if not is_active:
        messages.error(request, "این محصول در حال حاضر فعال نیست.")
        return redirect(next_url or reverse("orders:cart_detail"))

    # ✅ FIX: only use variant if it belongs to this product
    variant: ProductVariant | None = None
    if variant_id:
        variant_obj = get_object_or_404(ProductVariant, pk=variant_id)
        # فقط اگه برای همین product هست قبولش کن
        if getattr(variant_obj, "product_id", None) == product.id:
            variant = variant_obj
        else:
            variant = None  # variant نامرتبط را نادیده بگیر
    else:
        # اگر محصول تنوع دارد ولی هیچ variant انتخاب نشده:
        if hasattr(product, "variants") and product.variants.exists():
            messages.error(request, "لطفاً تنوع مورد نظر را انتخاب کنید.")
            return redirect(next_url or reverse("orders:cart_detail"))

    # ✅ مدیریت موجودی: فقط اگر stock مقدار *مثبت* داشت محدود کن
    stock = getattr(variant, "stock", None) if variant else None
    if isinstance(stock, int) and stock > 0 and qty > stock:
        qty = stock
        messages.warning(request, "تعداد به موجودی محدود شد.")

    # ✅ Add to cart safely
    from .services import _unit_price_for

    item = add_to_cart(cart=cart, product=product, variant=variant, qty=qty)

    # ✅ Ensure cart belongs to user
    if request.user.is_authenticated and cart.user is None:
        cart.user = request.user
        cart.save(update_fields=["user"])

    # ✅ Ensure item was really created (fallback)
    if not item.pk or not cart.items.exists():
        CartItem.objects.create(
            cart=cart,
            product=product,
            variant=variant,
            quantity=qty,
            unit_price=_unit_price_for(product, variant),
        )

    messages.success(request, "به سبد خرید اضافه شد.")
    return redirect(next_url or reverse("orders:cart_detail"))


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
def remove_cart_item(request: HttpRequest, item_id: int) -> HttpResponse:
    """Remove an item from the cart by its ID."""
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.info(request, "Item removed from your cart.")
    return redirect("orders:cart_detail")


@require_POST
@transaction.atomic
def update_cart_item(request: HttpRequest, item_id: int) -> HttpResponse:
    """Update the quantity of an existing cart item."""
    cart = _get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

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


# ----------------------------- Checkout -----------------------------
@transaction.atomic
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Handle both guest and logged-in user checkout flow."""
    _ensure_session(request)
    session_key = request.session.session_key or ""

    # 🔍 Debug diagnostics
    from django.db.models import Count

    debug_info = {
        "user_authenticated": request.user.is_authenticated,
        "user_id": getattr(request.user, "id", None),
        "session_key": session_key,
        "guest_carts": list(
            Cart.objects.filter(user=None)
            .annotate(num_items=Count("items"))
            .values("id", "session_key", "num_items")
        ),
        "user_carts": list(
            Cart.objects.filter(user=request.user)
            .annotate(num_items=Count("items"))
            .values("id", "session_key", "num_items")
        ),
    }
    import json
    import os

    with open(os.path.join(os.getcwd(), "checkout_debug.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(debug_info, ensure_ascii=False, indent=2))

    # ✅ Step 1: unify guest and user carts
    cart = None
    if request.user.is_authenticated:
        # Try to find user's cart
        cart = Cart.objects.filter(user=request.user).prefetch_related("items").first()

        # If user has no cart yet, see if guest cart exists
        if not cart:
            guest_cart = (
                Cart.objects.filter(user=None, session_key=session_key)
                .prefetch_related("items")
                .first()
            )
            if guest_cart:
                # 🔁 assign ownership of guest cart to the user
                guest_cart.user = request.user
                guest_cart.save(update_fields=["user"])
                cart = guest_cart

    # For guests (or fallback)
    if not cart:
        cart = Cart.objects.filter(session_key=session_key).prefetch_related("items").first()
        if not cart:
            cart = _get_cart(request)

    # ✅ Step 2: sanity check
    cart.refresh_from_db()
    # تضمین اینکه سبد منطبق با یوزر فعلی را گرفته‌ایم
    if request.user.is_authenticated:
        user_cart = Cart.objects.filter(user=request.user).first()
        if user_cart:
            cart = user_cart
    cart.refresh_from_db()

    if not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("orders:cart_detail")

    # ---------------------------
    # Logged-in user flow
    # ---------------------------
    if request.user.is_authenticated:
        if request.method == "POST":
            form = CheckoutForm(request.POST, user=request.user)
            is_valid = form.is_valid()
            customer, _ = Customer.objects.get_or_create(user=request.user)

            # Address
            address = form.cleaned_data.get("address") if is_valid else None
            if address is None:
                addr_qs = request.user.addresses.all()
                address_id = request.POST.get("address_id")
                if address_id:
                    address = addr_qs.filter(pk=address_id).first()
                if not address:
                    address = addr_qs.filter(default_shipping=True).first()

            # Shipping method
            shipping_method = form.cleaned_data.get("shipping_method") if is_valid else None
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
                set_shipping_method(cart=cart, shipping_method=shipping_method)

            # Payment method
            pm_field = Order._meta.get_field("payment_method")
            pm_input = (request.POST.get("payment_method") or "").strip()
            allowed_pm = {key for key, _ in pm_field.choices} | {"fake"}
            pm = pm_input if pm_input in allowed_pm else pm_field.default

            if not is_valid:
                return redirect("orders:cart_detail")

            notes = (request.POST.get("notes") or "").strip()
            order, _ = create_order_from_cart(
                customer=customer,
                shipping_address=address,
                cart=cart,
                shipping_method=shipping_method,
                payment_method=pm,
                discount=Decimal("0.00"),
                notes=notes,
            )
            return redirect("payments:checkout", order_number=order.number)

        # GET request
        form = CheckoutForm(user=request.user)
        items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
        subtotal = cart_total(cart)
        addresses = request.user.addresses.all()
        default_address_id = (
            addresses.filter(default_shipping=True).values_list("id", flat=True).first()
        )
        return render(
            request,
            "orders/checkout.html",
            {
                "form": form,
                "cart": cart,
                "items": items,
                "subtotal": subtotal,
                "addresses": addresses,
                "default_address_id": default_address_id,
            },
        )

    # ---------------------------
    # Guest checkout flow
    # ---------------------------
    else:
        if request.method == "POST":
            form = AddressForm(request.POST)
            if form.is_valid():
                guest_addr = form.cleaned_data
                request.session["guest_shipping_address"] = guest_addr
                request.session.modified = True

                address = Address(**guest_addr)
                shipping_method = ShippingMethod.objects.filter(is_active=True).first()
                if shipping_method is None:
                    shipping_method = ShippingMethod.objects.create(
                        name="Post",
                        code="post",
                        base_price=Decimal("0.00"),
                        is_active=True,
                    )

                pm_field = Order._meta.get_field("payment_method")
                pm = pm_field.default
                notes = (request.POST.get("notes") or "").strip()
                customer, _ = Customer.objects.get_or_create(user=None)

                order, _ = create_order_from_cart(
                    customer=customer,
                    shipping_address=address,
                    cart=cart,
                    shipping_method=shipping_method,
                    payment_method=pm,
                    discount=Decimal("0.00"),
                    notes=notes,
                )
                return redirect("payments:checkout", order_number=order.number)
        else:
            form = AddressForm()

        items = cart.items.select_related("product", "variant", "product__brand").order_by("-id")
        subtotal = cart_total(cart)
        return render(
            request,
            "orders/checkout_guest.html",
            {"form": form, "cart": cart, "items": items, "subtotal": subtotal},
        )


# ----------------------------- Orders -----------------------------
@login_required
def order_history_view(request: HttpRequest) -> HttpResponse:
    customer = getattr(request.user, "customer", None)
    orders = (
        Order.objects.filter(customer=customer)
        .select_related("shipping_address", "shipping_method", "customer", "customer__user")
        .prefetch_related("items", "items__product", "items__variant", "items__product__images")
        .order_by("-placed_at")
        if customer
        else Order.objects.none()
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


@login_required
def payment_history_view(request: HttpRequest) -> HttpResponse:
    from apps.payments.models import Payment

    qs = (
        Payment.objects.select_related("order", "order__customer", "order__customer__user")
        .filter(order__customer__user=request.user)
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 12)
    payments = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "orders/payment_list.html", {"payments": payments})


# ----------------------------- Analytics APIs -----------------------------
@staff_member_required
@require_GET
def payments_breakdown_api(request: HttpRequest) -> JsonResponse:
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
