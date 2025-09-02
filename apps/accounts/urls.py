from django.urls import path
from .views import (
    register_view,
    EmailLoginView,
    dashboard_view,
    profile_view,
    address_list_view,
    address_create_view,
    address_update_view,
    address_delete_view,
    MyPasswordResetView,
    MyPasswordResetDoneView,
    MyPasswordResetConfirmView,
    MyPasswordResetCompleteView,
    activate_account_view,
    resend_activation_view,
    register_view,
)

app_name = "accounts"

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("profile/", profile_view, name="profile"),
    path("addresses/", address_list_view, name="address_list"),
    path("addresses/create/", address_create_view, name="address_create"),
    path("addresses/<int:pk>/edit/", address_update_view, name="address_edit"),
    path("addresses/<int:pk>/delete/", address_delete_view, name="address_delete"),
    path("password-reset/", MyPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", MyPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        MyPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("reset/done/", MyPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("activate/<uidb64>/<token>/", activate_account_view, name="activate"),
    path("resend-activation/", resend_activation_view, name="resend_activation"),
]
