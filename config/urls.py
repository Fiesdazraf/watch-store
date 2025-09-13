"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

# config/urls.py
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthcheck(_):
    return HttpResponse("OK")


def home(_):
    return HttpResponse("<h1>Watch Store - Setup Complete (Phase 1)</h1>")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="health"),
    # ✅ namespace باید داخل include باشد (نه پارامتر path)
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("payments/", include(("apps.payments.urls", "payments"), namespace="payments")),
    path("backoffice/", include("apps.backoffice.urls", namespace="backoffice")),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("", home, name="home"),  # می‌تونی اینو بالا/پایین نگه داری
]
