from django.core.management.base import BaseCommand

from apps.payments.models import PaymentMethod

DEFAULTS = [
    {"name": "Online (Mock)", "code": "online", "is_active": True},
    {"name": "Cash on Delivery", "code": "cod", "is_active": True},
]


class Command(BaseCommand):
    help = "Seed payment methods"

    def handle(self, *args, **options):
        created = 0
        for item in DEFAULTS:
            obj, was_created = PaymentMethod.objects.get_or_create(code=item["code"], defaults=item)
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} payment methods."))
