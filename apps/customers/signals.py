import os

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Customer


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_customer_profile(sender, instance, created, **kwargs):
    # 🔒 جلوگیری از ساخت خودکار Customer در محیط تست
    if os.environ.get("PYTEST_RUNNING"):
        return

    if created:
        Customer.objects.get_or_create(user=instance)
