# config/urls.py
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.cache import cache_page

from apps.catalog.views import ProductListView


def healthcheck(_):
    return HttpResponse("OK")


def home(_):
    return HttpResponse("<h1>Watch Store - Setup Complete (Phase 1)</h1>")


# Option A) cache the CBV inline
cached_product_list = cache_page(60 * 2)(ProductListView.as_view())

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="health"),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("payments/", include(("apps.payments.urls", "payments"), namespace="payments")),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("", include(("apps.backoffice.urls", "backoffice"), namespace="backoffice")),
    path("products/", cached_product_list, name="product_list"),
    path("home/", home, name="home"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
]


if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
