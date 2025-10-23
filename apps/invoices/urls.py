# apps/invoices/urls.py
from django.urls import path

from .views import invoice_detail_view, invoice_list_view, invoice_pdf_view

app_name = "invoices"

urlpatterns = [
    # 📄 لیست فاکتورها (backoffice یا user-facing)
    path("", invoice_list_view, name="invoice_list"),
    # 🧾 جزئیات فاکتور خاص
    path("<str:number>/", invoice_detail_view, name="invoice_detail"),
    # 💾 دریافت PDF همان فاکتور
    path("<str:number>/pdf/", invoice_pdf_view, name="invoice_pdf"),
]
