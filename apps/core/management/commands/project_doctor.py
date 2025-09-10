from importlib import import_module

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import models
from django.urls import NoReverseMatch, reverse

REQUIRED_APPS = ["apps.payments", "apps.orders"]

REQUIRED_URLS = [
    ("payments:checkout", {"order_number": "SW00000001"}),
    ("payments:mock_gateway", {"order_number": "SW00000001"}),
    ("payments:success", {"order_number": "SW00000001"}),
    ("payments:failed", {"order_number": "SW00000001"}),
]


class Command(BaseCommand):
    help = "Run project health checks for orders/payments integration (new FK-based payments)."

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

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Models sanity checks =="))

        # --- payments.Payment checks
        try:
            payments_models = import_module("apps.payments.models")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing apps.payments.models: {e}"))
            return

        Payment = getattr(payments_models, "Payment", None)
        if not Payment:
            self.stdout.write(self.style.ERROR("apps.payments.models.Payment not found"))
            ok = False
        else:
            # order field: must be FK to orders.Order with related_name="payments"
            try:
                order_field = Payment._meta.get_field("order")
                if not isinstance(order_field, models.ForeignKey):
                    self.stdout.write(
                        self.style.ERROR("Payment.order must be a ForeignKey (not OneToOne).")
                    )
                    ok = False
                if (
                    order_field.related_model is None
                    or order_field.related_model.__name__ != "Order"
                ):
                    self.stdout.write(
                        self.style.ERROR("Payment.order is not related to orders.Order")
                    )
                    ok = False
                if getattr(order_field.remote_field, "related_name", None) != "payments":
                    self.stdout.write(
                        self.style.ERROR("Payment.order.related_name should be 'payments'")
                    )
                    ok = False
                else:
                    self.stdout.write(
                        self.style.SUCCESS("OK: Payment.order ForeignKey -> orders.Order(payments)")
                    )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error introspecting Payment.order: {e}"))
                ok = False

            # expected fields on Payment
            expected_fields = [
                "amount",
                "currency",
                "provider",
                "status",
                "external_id",
                "attempt_count",
                "max_attempts",
                "paid_at",
                "created_at",
                "updated_at",
            ]
            for fname in expected_fields:
                if not Payment._meta.get_fields():
                    self.stdout.write(self.style.ERROR("Payment has no fields?"))
                    ok = False
                    break
            for fname in expected_fields:
                try:
                    Payment._meta.get_field(fname)
                except Exception:
                    self.stdout.write(self.style.ERROR(f"Payment missing field: {fname}"))
                    ok = False
            if ok:
                self.stdout.write(self.style.SUCCESS("OK: Payment fields look good."))

        # --- avoid duplicate Payment model in orders app
        try:
            orders_models = import_module("apps.orders.models")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing apps.orders.models: {e}"))
            ok = False
            orders_models = None

        if orders_models and hasattr(orders_models, "Payment"):
            self.stdout.write(
                self.style.WARNING("Found apps.orders.models.Payment (consider removing/renaming).")
            )

        # --- Order checks
        if orders_models:
            Order = getattr(orders_models, "Order", None)
            if not Order:
                self.stdout.write(self.style.ERROR("apps.orders.models.Order not found"))
                ok = False
            else:
                # must have number field
                try:
                    Order._meta.get_field("number")
                except Exception:
                    self.stdout.write(self.style.ERROR("Order missing field: number"))
                    ok = False

                # prefer to have is_paid property/field
                if not hasattr(Order, "is_paid"):
                    self.stdout.write(
                        self.style.WARNING("Order missing 'is_paid' (property/field).")
                    )

                # must have total_payable or total_amount
                if not (hasattr(Order, "total_payable") or hasattr(Order, "total_amount")):
                    self.stdout.write(
                        self.style.ERROR("Order must have either 'total_payable' or 'total_amount'")
                    )
                    ok = False

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Final verdict =="))
        if ok:
            self.stdout.write(self.style.SUCCESS("All checks passed  🎉"))
        else:
            self.stdout.write(self.style.ERROR("Some checks failed"))
