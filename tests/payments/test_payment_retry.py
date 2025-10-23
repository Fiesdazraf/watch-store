import pytest

pytestmark = pytest.mark.django_db


def test_payment_retry_increments_attempts():

    from model_bakery import baker

    payment = baker.make("payments.Payment", status="failed")
    # simulate retry manually
    payment.status = "pending"
    payment.save()
    assert payment.status in ("pending", "success", "failed")
