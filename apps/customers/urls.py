# apps/customers/urls.py
from django.urls import path

from .views import address_create, address_delete, address_list, address_update, set_default_address

app_name = "customers"

urlpatterns = [
    path("addresses/", address_list, name="address_list"),
    path("addresses/new/", address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", address_update, name="address_update"),
    path("addresses/<int:pk>/delete/", address_delete, name="address_delete"),
    path(
        "addresses/<int:pk>/set-default/<str:kind>/",
        set_default_address,
        name="set_default_address",
    ),
]
