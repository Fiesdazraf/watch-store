import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_kpis_api_staff(client, django_user_model):
    staff = django_user_model.objects.create_user(email="s@s.com", password="x", is_staff=True)
    client.force_login(staff)
    url = reverse("backoffice:kpis_api")
    resp = client.get(url)
    assert resp.status_code == 200

    data = resp.json()
    # خروجی دقیق kpis()
    expected_keys = {
        "orders_today",
        "revenue_today",
        "orders_30d",
        "revenue_30d",
        "avg_order_value_30d",
    }
    assert expected_keys.issubset(data.keys())


@pytest.mark.django_db
def test_sales_api_staff(client, django_user_model):
    staff = django_user_model.objects.create_user(email="s@s.com", password="x", is_staff=True)
    client.force_login(staff)

    url = reverse("backoffice:sales_api")
    resp = client.get(url, {"days": 7}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert resp.status_code == 200

    payload = resp.json()
    assert "labels" in payload and isinstance(payload["labels"], list)
    assert "datasets" in payload and isinstance(payload["datasets"], list)
    for ds in payload["datasets"]:
        assert "label" in ds and "data" in ds and isinstance(ds["data"], list)
