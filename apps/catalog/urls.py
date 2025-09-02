from django.urls import path

from .views import ProductDetailView, ProductListView

app_name = "catalog"

urlpatterns = [
    # Products
    path("shop/", ProductListView.as_view(), name="product_list"),
    path("shop/<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
