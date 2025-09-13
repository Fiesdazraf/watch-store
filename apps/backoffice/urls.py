from django.urls import path

from .views import (
    dashboard_view,
    health,
    kpis_api,
    sales_api,
    set_status_redirect_view,
    set_status_view,
)

app_name = "backoffice"

urlpatterns = [
    path("", dashboard_view, name="dashboard"),
    path("health/", health, name="health"),
    path("api/kpis/", kpis_api, name="kpis_api"),
    path("api/sales/", sales_api, name="sales_api"),
    path(
        "orders/<int:order_id>/set-status/", set_status_view, name="set_status"
    ),  # AJAX request view
    path(
        "orders/<int:order_id>/set-status-redirect/",
        set_status_redirect_view,
        name="set_status_redirect",
    ),  # non-AJAX request view
]
