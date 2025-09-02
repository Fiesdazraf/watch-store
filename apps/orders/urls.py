from django.urls import path

from .views import (
    add_to_cart_view,
    cart_detail,
    order_detail_view,
    order_history_view,
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
]
