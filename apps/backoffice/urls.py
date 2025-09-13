from django.urls import path

from .views import dashboard_view, health, kpis_api, order_set_status_view, sales_api

app_name = "backoffice"

urlpatterns = [
    path("", dashboard_view, name="dashboard"),
    path("health/", health, name="health"),
    path("api/kpis/", kpis_api, name="kpis_api"),
    path("api/sales/", sales_api, name="sales_api"),
    path("orders/<int:order_id>/set-status/", order_set_status_view, name="order_set_status"),
]
