from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("shop/", views.ProductListView.as_view(), name="product_list"),
    path("shop/<slug:slug>/", views.ProductDetailView.as_view(), name="product_detail"),
]
