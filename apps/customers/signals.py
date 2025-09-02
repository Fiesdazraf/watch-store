# apps/customers/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Customer

User = get_user_model()


@receiver(post_save, sender=User)
def create_customer_for_user(sender, instance, created, **kwargs):
    if created:
        Customer.objects.get_or_create(user=instance)
