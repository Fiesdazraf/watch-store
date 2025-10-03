# config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path
from django.views.decorators.cache import cache_page

from apps.catalog.views import ProductListView


def healthcheck(_):
    return HttpResponse("OK")


def home(_):
    return HttpResponse("<h1>Watch Store - Setup Complete (Phase 1)</h1>")


# Option A) cache the CBV inline (kept if you want a fast products listing route)
cached_product_list = cache_page(60 * 2)(ProductListView.as_view())


def root_dispatch(request):
    """
    Smart root:
      - if authenticated staff -> backoffice dashboard
      - else -> public shop listing (catalog:product_list)
    """
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("backoffice:dashboard")
    return redirect("catalog:product_list")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="health"),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("payments/", include(("apps.payments.urls", "payments"), namespace="payments")),
    # keep catalog mounted where it currently expects to be (it defines /shop/ internally)
    path("catalog/", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    # mount orders and backoffice under explicit prefixes (avoid empty includes)
    path("orders/", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("backoffice/", include(("apps.backoffice.urls", "backoffice"), namespace="backoffice")),
    # optional: keep a short /products/ endpoint that renders product list (cached)
    path("products/", cached_product_list, name="product_list_short"),
    # smart root dispatch (public landing or staff dashboard)
    path("", root_dispatch, name="root_dispatch"),
    path("home/", home, name="home"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
