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
    assert "orders_today" in data and "revenue_today" in data


@pytest.mark.django_db
def test_sales_api_staff(client, django_user_model):
    staff = django_user_model.objects.create_user(email="s@s.com", password="x", is_staff=True)
    client.force_login(staff)
    url = reverse("backoffice:sales_api")
    resp = client.get(url, {"days": 7})
    assert resp.status_code == 200
    assert "series" in resp.json()
