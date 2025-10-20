import pytest
from django.urls import reverse
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_product_list_view(client):
    baker.make("catalog.Product", _quantity=3)
    url = reverse("catalog:product_list")
    response = client.get(url)
    assert response.status_code == 200
    assert "products" in response.context


def test_product_detail_view(client):
    from django.urls import reverse
    from model_bakery import baker

    product = baker.make("catalog.Product")
    url = reverse("catalog:product_detail", args=[product.pk, product.slug])
    response = client.get(url)

    assert response.status_code == 200
    # Use correct field name (adjust based on your model)
    name_field = getattr(product, "title", None) or getattr(product, "product_name", None)
    assert name_field and str(name_field) in response.content.decode()
