import pytest
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_invoice_attached_to_order():
    order = baker.make("orders.Order")
    invoice = baker.make("invoices.Invoice", order=order)
    assert invoice.order.id == order.id
