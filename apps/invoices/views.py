# apps/invoices/views.py
from __future__ import annotations

import io

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import Invoice


def invoice_list_view(request):
    invoices = Invoice.objects.select_related("order").all()
    return render(request, "invoices/invoice_list.html", {"invoices": invoices})


@login_required
def invoice_detail_view(request: HttpRequest, number: str) -> HttpResponse:
    inv = get_object_or_404(Invoice, number=number)
    # (Optional) access control: e.g., only owner or staff
    if not request.user.is_staff:
        # if your Invoice has order->customer->user relation, check it:
        order = getattr(inv, "order", None)
        user_id = getattr(getattr(getattr(order, "customer", None), "user", None), "id", None)
        if user_id != request.user.id:
            raise Http404()
    return render(request, "invoices/invoice_detail.html", {"invoice": inv})


@login_required
def invoice_pdf_view(request: HttpRequest, number: str) -> HttpResponse:
    inv = get_object_or_404(Invoice, number=number)
    if not request.user.is_staff:
        order = getattr(inv, "order", None)
        user_id = getattr(getattr(getattr(order, "customer", None), "user", None), "id", None)
        if user_id != request.user.id:
            raise Http404()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Invoice #{inv.number}")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Status: {inv.get_status_display()}")
    y -= 16
    if inv.issued_at:
        c.drawString(40, y, f"Issued at: {inv.issued_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 16
    if inv.paid_at:
        c.drawString(40, y, f"Paid at: {inv.paid_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 16

    c.drawString(40, y, f"Amount: {inv.amount}")
    y -= 24

    # (Optional) Order information
    order = getattr(inv, "order", None)
    if order:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, f"Order #{getattr(order, 'number', order.id)}")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"Total: {order.grand_total}")
        y -= 16

    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="invoice_{inv.number}.pdf"'
    return resp
