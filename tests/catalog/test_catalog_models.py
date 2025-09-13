import pytest

pytestmark = pytest.mark.django_db


def test_product_and_variant_active(product, variant):
    assert product.is_active is True
    assert variant.is_active is True
    assert variant.product == product


def test_variant_price_snapshot(product, variant):
    # If you have helper to compute final price = product.price + variant.extra_price
    base = product.price
    extra = variant.extra_price
    total = base + extra
    assert float(total) == float(base) + float(extra)
