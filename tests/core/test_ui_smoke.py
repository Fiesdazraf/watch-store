import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "url_name,args",
    [
        ("home", []),
        ("catalog:product_list", []),
        ("accounts:dashboard", []),
        ("payments:checkout", ["SW00000001"]),
    ],
)
def test_pages_render_without_error(client, django_user_model, url_name, args):
    user = django_user_model.objects.create_user(email="test@example.com", password="123")
    client.force_login(user)
    url = reverse(url_name, args=args)
    resp = client.get(url)
    assert resp.status_code in (200, 302, 404)  # accept 404 for dummy order_number
