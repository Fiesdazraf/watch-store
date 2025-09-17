import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_dashboard_template_renders_sections(client, staff_user):
    client.force_login(staff_user)
    url = reverse("backoffice:dashboard")
    resp = client.get(url)
    html = resp.content.decode("utf-8")

    # QA: وجود بخش‌های کلیدی
    assert "داشبورد" in html
    assert "مجموع فروش" in html
    assert "تعداد سفارش‌ها" in html
    assert "میانگین ارزش سفارش" in html
    assert "نمودار فروش" in html or "فروش ۳۰ روز اخیر" in html
    assert "سفارش‌های اخیر" in html
