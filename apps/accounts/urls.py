from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    EmailLoginView,
    MyPasswordResetCompleteView,
    MyPasswordResetConfirmView,
    MyPasswordResetDoneView,
    MyPasswordResetView,
    activate_account_view,
    address_create_view,
    address_delete_view,
    address_list_view,
    address_update_view,
    dashboard_view,
    profile_view,
    register_view,
    resend_activation_view,
)

app_name = "accounts"

urlpatterns = [
    # Auth & profile
    path("register/", register_view, name="register"),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="accounts:login"), name="logout"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("profile/", profile_view, name="profile"),
    # Addresses
    path("addresses/", address_list_view, name="address_list"),
    path("addresses/create/", address_create_view, name="address_create"),
    path("addresses/<int:pk>/edit/", address_update_view, name="address_update"),
    path("addresses/<int:pk>/delete/", address_delete_view, name="address_delete"),
    # Password reset
    path("password-reset/", MyPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", MyPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        MyPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("reset/done/", MyPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    # Email activation
    path("activate/<uidb64>/<token>/", activate_account_view, name="activate"),
    path("resend-activation/", resend_activation_view, name="resend_activation"),
]
