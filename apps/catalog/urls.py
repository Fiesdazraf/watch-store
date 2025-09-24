# apps/catalog/urls.py
from django.urls import path

from .views import ProductDetailView, ProductListView

app_name = "catalog"

urlpatterns = [
    path("shop/", ProductListView.as_view(), name="product_list"),
    path("shop/<int:pk>-<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
