import pytest

pytestmark = pytest.mark.django_db


def test_add_to_cart_adds_new_item(cart, product, variant):
    from apps.orders import services

    item = services.add_to_cart(cart=cart, product=product, variant=variant, qty=2)
    cart.refresh_from_db()

    assert item.quantity == 2
    assert item.product == product
    assert item.variant == variant

    # Common policy: unit_price snapshot = product.price + variant.extra_price
    expected_unit = product.price + variant.extra_price
    assert float(item.unit_price) == float(expected_unit)


def test_add_to_cart_merges_same_item(cart, product, variant):
    from apps.orders import services

    services.add_to_cart(cart=cart, product=product, variant=variant, qty=1)
    item2 = services.add_to_cart(cart=cart, product=product, variant=variant, qty=3)
    item2.refresh_from_db()
    assert item2.quantity == 4  # merged


def test_cart_total_includes_items_and_shipping(cart, product, variant, shipping_method):
    from apps.orders import services

    services.add_to_cart(cart=cart, product=product, variant=variant, qty=1)
    # Assuming a method to set shipping on cart or a service
    services.set_shipping_method(cart=cart, shipping_method=shipping_method)

    cart.refresh_from_db()
    # expected = (product.price + variant.extra_price) * qty + shipping.base_price
    expected = (product.price + variant.extra_price) * 1 + shipping_method.base_price
    assert float(cart.total_amount) == float(expected)
