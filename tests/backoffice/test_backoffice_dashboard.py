# tests/backoffice/test_backoffice_dashboard.py
from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_dashboard_kpis_and_chart_requires_staff(client):
    url = reverse("backoffice:dashboard")
    resp = client.get(url)
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_dashboard_kpis_and_chart(client, django_user_model):
    # ساخت کاربر استاف با مدل سفارشی پروژه
    user = django_user_model.objects.create_user(
        **{
            # اگر USERNAME_FIELD=email است، همین کافیست
            getattr(django_user_model, "USERNAME_FIELD", "username"): "staff@example.com",
            "password": "x",
            "is_staff": True,
        }
    )
    # لاگین مستقیم بدون درگیری با backend
    client.force_login(user)

    url = reverse("backoffice:dashboard")
    resp = client.get(url)
    assert resp.status_code == 200

    html = resp.content.decode("utf-8")
    assert "سفارش‌های اخیر" in html
    assert "نمودار فروش" in html or "فروش ۳۰ روز اخیر" in html
