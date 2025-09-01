# apps/accounts/signals.py (یا هر جا که لاگین هندل می‌کنی)
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

@receiver(user_logged_in)
def merge_session_cart_to_user(sender, request, user, **kwargs):
    from apps.orders.models import Cart, CartItem
    from apps.catalog.models import ProductVariant

    session_cart = request.session.get("cart", [])
    if not session_cart:
        return

    # پیدا کردن/ساخت Cart فعال برای این یوزر
    cart, _ = Cart.objects.get_or_create(user=user, session_key="", defaults={})

    for item in session_cart:
        product_id = item.get("product_id")
        variant_id = item.get("variant_id")
        qty = int(item.get("qty", 1))

        if qty < 1 or not product_id:
            continue

        variant = None
        if variant_id:
            try:
                variant = ProductVariant.objects.get(pk=variant_id)
            except ProductVariant.DoesNotExist:
                variant = None

        # snapshot price را خودت داخل service تعیین کن
        # اگر service داری، اینجا از add_to_cart استفاده کن:
        # from apps.orders.models import add_to_cart
        # add_to_cart(cart, Product.objects.get(pk=product_id), variant, qty)
        # اینجا نسخه‌ی مینیمال (بدون قیمت داینامیک):
        ci, created = CartItem.objects.get_or_create(
            cart=cart, product_id=product_id, variant=variant, defaults={"quantity": qty}
        )
        if not created:
            ci.quantity += qty
        ci.save()

    request.session["cart"] = []
    request.session.modified = True
