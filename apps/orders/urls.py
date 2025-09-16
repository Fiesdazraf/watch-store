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
    remove_from_cart_view,
    update_cart_item,
)

app_name = "orders"

urlpatterns = [
    path("cart/", cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", add_to_cart_view, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", update_cart_item, name="update_cart_item"),
    path("cart/item/<int:item_id>/remove/", remove_cart_item, name="remove_cart_item"),
    path("cart/items/<int:pk>/remove/", remove_from_cart_view, name="remove_from_cart"),
    path("checkout/", checkout_view, name="checkout"),
    # تاریخچه سفارش‌ها
    path("account/orders/", order_history_view, name="history"),
    path("account/orders/<str:number>/", order_detail_view, name="detail"),
    # 🔁 alias برای سازگاری با تست‌های قدیمی
    path("orders/", order_history_view, name="list"),  # <- اضافه شد (back-compat)
    path("payments/", payment_history_view, name="payments"),
    path("thanks/<str:number>/", order_thanks_view, name="thanks"),
]
