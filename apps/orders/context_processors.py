from .models import Cart


def cart_summary(request):
    """
    Provides a cart summary (total_qty + total_price) available in all templates.
    For guests → session cart, for logged-in users → DB cart.
    """
    total_qty = 0
    total_price = 0

    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user).first()
        else:
            cart_id = request.session.get("cart_id")
            cart = Cart.objects.filter(id=cart_id).first() if cart_id else None

        if cart:
            total_qty = sum(item.qty for item in cart.items.all())
            total_price = sum(item.qty * item.unit_price for item in cart.items.all())

    except Exception:
        # fallback if something goes wrong
        pass

    return {
        "cart_summary": {
            "total_qty": total_qty,
            "total_price": total_price,
        }
    }
