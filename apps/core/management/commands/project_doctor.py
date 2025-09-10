from importlib import import_module

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import models
from django.urls import NoReverseMatch, reverse

REQUIRED_APPS = ["apps.payments", "apps.orders"]  # also ensure orders is installed
REQUIRED_URLS = [
    ("payments:checkout_payment", {"order_number": "SW00000001"}),
    ("payments:success", {"order_number": "SW00000001"}),
    ("payments:failed", {"order_number": "SW00000001"}),
]


class Command(BaseCommand):
    help = "Run project health checks for orders/payments integration."

    def handle(self, *args, **options):
        ok = True

        self.stdout.write(self.style.MIGRATE_HEADING("== Installed apps =="))
        for app in REQUIRED_APPS:
            if not django_apps.is_installed(app):
                self.stdout.write(self.style.ERROR(f"Missing in INSTALLED_APPS: {app}"))
                ok = False
            else:
                self.stdout.write(self.style.SUCCESS(f"OK: {app}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n== URLs existence =="))
        for name, kwargs in REQUIRED_URLS:
            try:
                reverse(name, kwargs=kwargs)
                self.stdout.write(self.style.SUCCESS(f"OK: url '{name}'"))
            except NoReverseMatch:
                self.stdout.write(self.style.ERROR(f"Missing url name: {name}"))
                ok = False

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Orders/Payments models =="))

        # payments.Payment existence + OneToOne to orders.Order
        payments_models = None
        try:
            payments_models = import_module("apps.payments.models")
            Payment = getattr(payments_models, "Payment", None)
            if not Payment:
                self.stdout.write(self.style.ERROR("apps.payments.models.Payment not found"))
                ok = False
            else:
                try:
                    field = Payment._meta.get_field("order")
                    # Check OneToOneField
                    if not isinstance(field, models.OneToOneField):
                        self.stdout.write(self.style.ERROR("Payment.order must be OneToOneField"))
                        ok = False
                    # Check related model
                    if field.related_model is None or field.related_model.__name__ != "Order":
                        self.stdout.write(
                            self.style.ERROR("Payment.order is not related to orders.Order")
                        )
                        ok = False
                    # Check related_name
                    if field.remote_field.related_name != "payment":
                        self.stdout.write(
                            self.style.ERROR("Payment.order.related_name should be 'payment'")
                        )
                        ok = False
                    if ok:
                        self.stdout.write(
                            self.style.SUCCESS(
                                "OK: payments.Payment.order OneToOne -> orders.Order(payment)"
                            )
                        )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error introspecting Payment.order: {e}"))
                    ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing apps.payments.models: {e}"))
            ok = False

        # check duplicate orders.Payment
        orders_models = None
        try:
            orders_models = import_module("apps.orders.models")
            if hasattr(orders_models, "Payment"):
                self.stdout.write(
                    self.style.WARNING(
                        "Found apps.orders.models.Payment (consider removing/renaming)."
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing apps.orders.models: {e}"))
            ok = False

        # Order helpers exist? (only if we imported orders models successfully)
        if orders_models:
            Order = getattr(orders_models, "Order", None)
            required_attrs = [
                "get_checkout_payment_url",
                "get_payment_success_url",
                "get_payment_failed_url",
                "is_paid",
                "payment_obj",
                "payment_status",
                "total_payable",
            ]
            if Order:
                for attr in required_attrs:
                    if not hasattr(Order, attr):
                        self.stdout.write(
                            self.style.ERROR(f"Order missing method/property: {attr}")
                        )
                        ok = False
                if ok:
                    self.stdout.write(
                        self.style.SUCCESS("OK: Order helpers exist (if no errors above).")
                    )
            else:
                self.stdout.write(self.style.ERROR("apps.orders.models.Order not found"))
                ok = False

            self.stdout.write(self.style.MIGRATE_HEADING("\n== Final verdict =="))
            if ok:
                self.stdout.write(self.style.SUCCESS("All checks passed  🎉"))
                return
            else:
                self.stdout.write(self.style.ERROR("Some checks failed"))
                return
