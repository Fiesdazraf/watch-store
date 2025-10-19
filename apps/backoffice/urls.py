# apps/backoffice/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    dashboard_view,
    export_sales_csv_view,
    export_sales_pdf_view,
    export_sales_xlsx_view,
    health,
    invoices_api,
    invoices_list_view,
    kpis_api,
    orders_status_api,
    payments_breakdown_api,
    reports_view,
    sales_api,
    set_status_redirect_view,
    set_status_view,
)

app_name = "backoffice"

urlpatterns = [
    path("health/", health, name="health"),
    path("", dashboard_view, name="dashboard"),
    path("kpis/", kpis_api, name="kpis_api"),
    path("sales-api/", sales_api, name="sales_api"),
    path("api/payments-breakdown/", payments_breakdown_api, name="payments_breakdown_api"),
    path("api/orders-status/", orders_status_api, name="orders_status_api"),
    path("reports/", reports_view, name="reports"),
    path("reports/export/csv/", export_sales_csv_view, name="reports_export_csv"),
    path("export-sales-csv/", export_sales_csv_view, name="export_sales_csv"),
    path("orders/<int:order_id>/status/", set_status_redirect_view, name="set_status_redirect"),
    path("api/invoices/", invoices_api, name="invoices_api"),
    path("api/orders/<int:order_id>/status/", set_status_view, name="set_status"),
    path("export-sales-xlsx/", export_sales_xlsx_view, name="export_sales_xlsx"),
    path("export-sales-pdf/", export_sales_pdf_view, name="export_sales_pdf"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
    path("invoices/", invoices_list_view, name="invoices_list"),
]
