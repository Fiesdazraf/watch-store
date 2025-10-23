# apps/invoices/views.py
from __future__ import annotations

import io

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
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
    """
    فاکتور PDF با طراحی حرفه‌ای و فونت فارسی Watch-Store
    """
    inv = get_object_or_404(Invoice, number=number)

    # کنترل دسترسی
    if not request.user.is_staff:
        order = getattr(inv, "order", None)
        user_id = getattr(getattr(getattr(order, "customer", None), "user", None), "id", None)
        if user_id != request.user.id:
            raise Http404()

    # ---- PDF setup ----
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    # ثبت فونت فارسی (در اینجا HeiseiMin-W3 برای پشتیبانی Unicode)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

    # رنگ‌ها و استایل برند
    gold = colors.Color(0.79, 0.64, 0.15)
    grey = colors.Color(0.25, 0.25, 0.25)
    light_grey = colors.Color(0.85, 0.85, 0.85)

    # ---- Header ----
    c.setFont("HeiseiMin-W3", 20)
    c.setFillColor(gold)
    c.drawRightString(width - margin, y, "Watch-Store")
    y -= 25
    c.setFillColor(grey)
    c.setFont("HeiseiMin-W3", 13)
    c.drawString(margin, y, f"فاکتور فروش #{inv.number}")
    y -= 10
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    c.line(margin, y, width - margin, y)
    y -= 25

    # ---- Invoice Meta ----
    c.setFont("HeiseiMin-W3", 11)
    c.setFillColor(colors.black)
    if inv.issued_at:
        c.drawString(margin, y, f"تاریخ صدور: {inv.issued_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 16
    if inv.paid_at:
        c.drawString(margin, y, f"تاریخ پرداخت: {inv.paid_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 16
    c.drawString(margin, y, f"مبلغ کل: {inv.amount:,.0f} تومان")
    y -= 16
    c.drawString(margin, y, f"وضعیت: {inv.get_status_display()}")
    y -= 28

    # ---- Order Info ----
    order = getattr(inv, "order", None)
    if order:
        c.setFillColor(gold)
        c.setFont("HeiseiMin-W3", 13)
        c.drawString(margin, y, "جزئیات سفارش")
        y -= 16
        c.setFont("HeiseiMin-W3", 10)
        c.setFillColor(grey)
        c.drawString(margin, y, f"شماره سفارش: {order.number}")
        y -= 14
        c.drawString(margin, y, f"تاریخ ثبت: {order.placed_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 14
        c.drawString(margin, y, f"مبلغ سفارش: {order.grand_total:,.0f} تومان")
        y -= 24

        # ---- Order Items ----
        items = getattr(order, "items", None)
        if items and hasattr(items, "all"):
            c.setFont("HeiseiMin-W3", 10)
            c.setFillColor(colors.black)
            c.drawString(margin, y, "اقلام:")
            y -= 16
            c.setFont("HeiseiMin-W3", 9)

            for it in order.items.all():
                line = f"- {it.product.name} × {it.quantity} = {it.line_total:,.0f} تومان"
                c.drawString(margin + 10, y, line)
                y -= 12
                if y < 80:
                    c.showPage()
                    y = height - margin

    # ---- Footer ----
    c.setStrokeColor(light_grey)
    c.setLineWidth(0.8)
    c.line(margin, 60, width - margin, 60)
    c.setFont("HeiseiMin-W3", 9)
    c.setFillColor(grey)
    c.drawCentredString(
        width / 2, 45, "این فاکتور به صورت الکترونیکی صادر شده است و نیازی به مهر ندارد."
    )
    c.setFillColor(gold)
    c.drawCentredString(width / 2, 30, "© Watch-Store 2025  •  www.watchstore.com")

    # پایان و ذخیره PDF
    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{inv.number}.pdf"'
    return response
