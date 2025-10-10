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
    path("cart/", cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", add_to_cart_view, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", update_cart_item, name="update_cart_item"),
    path("remove/<int:item_id>/", remove_cart_item, name="remove_from_cart"),
    path("checkout/", checkout_view, name="checkout"),
    path("account/orders/", order_history_view, name="history"),
    path("account/orders/<str:number>/", order_detail_view, name="detail"),
    # برای سازگاری با تست‌ها
    path("orders/", order_history_view, name="list"),
    path("orders/<str:number>/", order_detail_view, name="order_detail"),
    path("payments/", payment_history_view, name="payments"),
    path("thanks/<str:number>/", order_thanks_view, name="thanks"),
]
