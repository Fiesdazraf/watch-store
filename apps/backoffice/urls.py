# apps/backoffice/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    dashboard_view,
    export_sales_csv_view,
    health,
    kpis_api,
    reports_view,
    sales_api,
    set_status_redirect_view,
    set_status_view,
)

app_name = "backoffice"

urlpatterns = [
    path("health/", health, name="health"),
    path("", dashboard_view, name="dashboard"),
    path("api/kpis/", kpis_api, name="kpis_api"),
    path("api/sales/", sales_api, name="sales_api"),
    path("reports/", reports_view, name="reports"),
    path("reports/export/csv/", export_sales_csv_view, name="reports_export_csv"),
    path("export-sales-csv/", export_sales_csv_view, name="export_sales_csv"),
    path("orders/<int:order_id>/status/", set_status_redirect_view, name="set_status_redirect"),
    path("api/orders/<int:order_id>/status/", set_status_view, name="set_status"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
]
