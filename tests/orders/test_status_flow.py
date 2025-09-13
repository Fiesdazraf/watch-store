import pytest
from django.core import mail


@pytest.mark.django_db
def test_order_status_flow_sends_email(order_factory, user_factory):
    user = user_factory(email="u@u.com")
    order = order_factory(user=user, status="pending", payment_status="paid")
    assert len(mail.outbox) == 0
    order.set_status("processing")
    assert len(mail.outbox) == 1
    assert "status changed" in mail.outbox[0].subject.lower()
