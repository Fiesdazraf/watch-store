# apps/invoices/utils/pdf.py
import os
import tempfile

from django.conf import settings
from django.template.loader import get_template
from weasyprint import CSS, HTML


def render_invoice_pdf(invoice):
    """
    Generates a PDF file for a given invoice object using the invoice_pdf.html template.
    Returns a tuple: (pdf_file_path, filename)
    """

    # 1️⃣ Load template & context
    template = get_template("invoices/invoice_pdf.html")
    context = {"invoice": invoice}
    html_string = template.render(context)

    # 2️⃣ Create temp file
    tmp_dir = tempfile.gettempdir()
    filename = f"invoice_{invoice.number}.pdf"
    pdf_path = os.path.join(tmp_dir, filename)

    # 3️⃣ Build full HTML to PDF
    html = HTML(string=html_string, base_url=settings.STATIC_ROOT)
    css = CSS(
        string="""
        @page { size: A4; margin: 25mm 20mm; }
        body { font-family: Vazirmatn, sans-serif; direction: rtl; }
    """
    )

    html.write_pdf(pdf_path, stylesheets=[css])
    return pdf_path, filename
