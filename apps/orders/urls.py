# apps/orders/urls.py
from django.urls import path

from .views import (
    add_to_cart_view,
    cart_detail,
    checkout_view,
    order_detail_view,
    order_history_view,
    order_thanks_view,
    payment_history_view,
    remove_cart_item,
    update_cart_item,
)

app_name = "orders"

urlpatterns = [
    # ------------------------------
    # Cart
    # ------------------------------
    path("cart/", cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", add_to_cart_view, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", update_cart_item, name="update_cart_item"),
    path("cart/item/<int:item_id>/remove/", remove_cart_item, name="remove_cart_item"),
    # 👇 alias برای تست‌ها (برخی تست‌ها دنبال remove_from_cart می‌گردند)
    path("cart/remove/<int:item_id>/", remove_cart_item, name="remove_from_cart"),
    # ------------------------------
    # Orders
    # ------------------------------
    path("orders/", order_history_view, name="order_history"),
    path("orders/<str:number>/", order_detail_view, name="order_detail"),
    path("checkout/", checkout_view, name="checkout"),
    path("thanks/<str:number>/", order_thanks_view, name="thanks"),
    # ------------------------------
    # Payments (history view only — checkout/success/failed in apps.payments)
    # ------------------------------
    path("payments/", payment_history_view, name="payments"),
]
