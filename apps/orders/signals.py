# apps/orders/signals.py
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

# از transaction دیگر استفاده نکنیم برای on_commit
from .models import Order


@receiver(pre_save, sender=Order)
def remember_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.only("status").get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Order)
def send_status_change_email(sender, instance: Order, created, **kwargs):
    if created:
        return
    old = getattr(instance, "_old_status", None)
    if not old or old == instance.status:
        return

    user = getattr(getattr(instance, "customer", None), "user", None)
    email = getattr(user, "email", None)
    if not email:
        return

    # بلافاصله ارسال کن تا داخل تست هم درجا داخل mail.outbox ثبت شود
    send_mail(
        subject=f"Order {instance.number} status changed",
        message=f"Your order is now '{instance.get_status_display()}'.",
        from_email=None,  # از DEFAULT_FROM_EMAIL استفاده میشه
        recipient_list=[email],
        fail_silently=True,
    )
