import pytest
from django.urls import reverse
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_sales_api_returns_filtered_data(client, admin_user):
    baker.make("orders.Order", grand_total=200)
    client.force_login(admin_user)
    url = reverse("backoffice:sales_api") + "?days=7"
    response = client.get(url)
    assert response.status_code == 200
    assert "labels" in response.json()
