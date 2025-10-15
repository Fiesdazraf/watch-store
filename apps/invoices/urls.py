# apps/invoices/urls.py
from django.urls import path

from .views import (
    invoice_detail_view,
    invoice_list_view,
    invoice_pdf_view,
)

app_name = "invoices"

urlpatterns = [
    path("", invoice_list_view, name="invoice_list"),
    path("<str:number>/", invoice_detail_view, name="invoice_detail"),
    path("<str:number>/pdf/", invoice_pdf_view, name="invoice_pdf"),
]
