# apps/customers/urls.py
from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("addresses/", views.address_list_view, name="address_list"),
    path("addresses/new/", views.address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_update, name="address_update"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path(
        "addresses/<int:pk>/set-default/<str:kind>/",
        views.set_default_address,
        name="set_default_address",
    ),
]
