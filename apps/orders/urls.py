from django.urls import path
from .views import cart_detail, add_to_cart_view, update_cart_item, remove_cart_item, order_history_view, order_detail_view

app_name = "orders"

urlpatterns = [
    path("cart/", cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", add_to_cart_view, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", update_cart_item, name="update_cart_item"),
    path("cart/item/<int:item_id>/remove/", remove_cart_item, name="remove_cart_item"),

    path("history/", order_history_view, name="order_history"),
    path("<str:number>/", order_detail_view, name="order_detail"),  # با number
]
