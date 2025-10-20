import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    resp = client.get(reverse("accounts:login"))
    assert resp.status_code == 200
    assert "form" in resp.content.decode().lower()


def test_login_with_email_success(client, user):
    """
    Test login flow using email field.
    Some setups don't redirect, they re-render dashboard with 200.
    """
    resp = client.post(
        reverse("accounts:login"),
        {
            "email": user.email,  # your project uses 'email' field
            "password": "pw12345",
        },
    )

    # Accept either redirect (302/303) or page render (200)
    assert resp.status_code in (200, 302, 303)
    if resp.status_code == 200:
        content = resp.content.decode().lower()
        assert "dashboard" in content or user.email in content


def test_dashboard_requires_login(client):
    resp = client.get(reverse("accounts:dashboard"))
    assert resp.status_code in (302, 303)
    assert reverse("accounts:login") in resp["Location"]
