from django.core.management.base import BaseCommand

from apps.orders.models import ShippingMethod


class Command(BaseCommand):
    help = "Seed default shipping methods"

    def handle(self, *args, **options):
        data = [
            ("Post (Standard)", "post-standard", "150000"),
            ("Tipax (Express)", "tipax-express", "290000"),
            ("In-store Pickup", "pickup", "0"),
        ]
        created = 0
        for name, code, price in data:
            obj, was_created = ShippingMethod.objects.get_or_create(
                code=code, defaults={"name": name, "base_price": price, "is_active": True}
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}"))
