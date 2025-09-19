import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_dashboard_renders(client, django_user_model):
    django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    client.login(email="staff@example.com", password="x")
    resp = client.get(reverse("backoffice:dashboard"))
    assert resp.status_code == 200
    assert b'name="start"' in resp.content
    assert b'name="end"' in resp.content


@pytest.mark.django_db
def test_reports_page_has_export_links(client, django_user_model):
    django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    client.login(email="staff@example.com", password="x")
    resp = client.get(reverse("backoffice:reports"))
    assert resp.status_code == 200
    assert b"Export CSV" in resp.content
    assert b"Export Excel" in resp.content
    assert b"Export PDF" in resp.content
