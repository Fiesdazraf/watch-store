from django.urls import path

from .views import (
    add_to_cart_view,
    cart_detail,
    checkout_view,
    order_detail_view,
    order_history_view,
    order_thanks_view,
    payment_fake_gateway_view,
    payment_return_view,
    remove_cart_item,
    update_cart_item,
)

app_name = "orders"

urlpatterns = [
    # Cart
    path("cart/", cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", add_to_cart_view, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", update_cart_item, name="update_cart_item"),
    path("cart/item/<int:item_id>/remove/", remove_cart_item, name="remove_cart_item"),
    # Orders
    path("history/", order_history_view, name="order_history"),
    path("orders/<str:number>/", order_detail_view, name="order_detail"),
    path("checkout/", checkout_view, name="checkout"),
    path("payment/return/", payment_return_view, name="payment_return"),
    # local demo gateway
    path("payment/fake/", payment_fake_gateway_view, name="payment_fake"),
    # simple thank you page
    path("thanks/<str:number>/", order_thanks_view, name="thanks"),
]
