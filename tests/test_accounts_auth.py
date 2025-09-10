import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    resp = client.get(reverse("accounts:login"))
    assert resp.status_code == 200
    assert "form" in resp.content.decode().lower()


def test_login_with_email_success(client, user):
    resp = client.post(reverse("accounts:login"), {"username": user.email, "password": "pw12345"})
    # Many setups redirect to dashboard on success
    assert resp.status_code in (302, 303)


def test_dashboard_requires_login(client):
    resp = client.get(reverse("accounts:dashboard"))
    # Expect redirect to login
    assert resp.status_code in (302, 303)
    assert reverse("accounts:login") in resp["Location"]
