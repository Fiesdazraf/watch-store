from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path
from django.views.decorators.cache import cache_page

from apps.catalog.views import ProductListView, home_view


def healthcheck(_):
    return HttpResponse("OK")


def home(_):
    return HttpResponse("<h1>Watch Store - Setup Complete (Phase 1)</h1>")


cached_product_list = cache_page(60 * 2)(ProductListView.as_view())


def root_dispatch(request):
    """Smart redirect for staff or public users."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("backoffice:dashboard")
    return redirect("catalog:product_list")


urlpatterns = [
    path("", home_view, name="home"),  # 🟢 حالا صفحه‌ی اصلی با home.html نمایش داده میشه
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="health"),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("customers/", include(("apps.customers.urls", "customers"), namespace="customers")),
    path("payments/", include(("apps.payments.urls", "payments"), namespace="payments")),
    path("catalog/", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("orders/", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("backoffice/", include(("apps.backoffice.urls", "backoffice"), namespace="backoffice")),
    path("invoices/", include(("apps.invoices.urls", "invoices"), namespace="invoices")),
    path("products/", cached_product_list, name="product_list_short"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
