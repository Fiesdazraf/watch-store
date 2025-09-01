from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

@receiver(user_logged_in)
def merge_session_cart_to_user(sender, request, user, **kwargs):
    """
    Example:
    - Read session cart (e.g., request.session.get("cart"))
    - Merge items into user's persistent cart model
    - Clear session cart after success
    """
    session_cart = request.session.get("cart")
    if not session_cart:
        return

    # Pseudo-code: adapt to your Cart/CartItem models
    try:
        from orders.models import Cart, CartItem, ProductVariant  # adjust paths
    except Exception:
        return

    cart, _ = Cart.objects.get_or_create(user=user, is_active=True)
    for item in session_cart:
        variant_id = item.get("variant_id")
        qty = int(item.get("qty", 1))
        if not variant_id or qty < 1:
            continue
        # ensure variant exists
        try:
            variant = ProductVariant.objects.get(pk=variant_id)
        except ProductVariant.DoesNotExist:
            continue
        cart_item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)
        if not created:
            cart_item.quantity += qty
        else:
            cart_item.quantity = qty
        cart_item.save()

    # clear session cart
    request.session["cart"] = []
    request.session.modified = True
