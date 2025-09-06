from django.urls import path

from .views import (
    checkout_payment_view,
    mock_gateway_view,
    payment_failed_view,
    payment_success_view,
)

app_name = "payments"

urlpatterns = [
    path("checkout/<str:order_number>", checkout_payment_view, name="checkout_payment"),
    path("mock-gateway/<str:order_number>", mock_gateway_view, name="mock_gateway"),
    path("success/<str:order_number>", payment_success_view, name="success"),
    path(
        "failed/<str:order_number>", payment_failed_view, name="failed"
    ),  # Add the new view path here.  # Updated
]
