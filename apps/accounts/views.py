from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .forms import AddressForm, ProfileForm, RegisterForm
from .models import Address

User = get_user_model()


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # NOTE: RegisterForm.save(commit=False) already sets hashed password
        user = form.save(commit=False)
        user.is_active = False
        user.email_verified = False
        user.save()

        current_site = get_current_site(request)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activation_url = reverse("accounts:activate", args=[uid, token])
        activation_link = f"{request.scheme}://{current_site.domain}{activation_url}"

        subject = render_to_string(
            "accounts/emails/activation_subject.txt", {"site_name": current_site.name}
        ).strip()
        message = render_to_string(
            "accounts/emails/activation_email.txt",
            {"user": user, "activation_link": activation_link, "site_name": current_site.name},
        )
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

        messages.info(request, "A verification email has been sent. Please check your inbox.")
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    # نکته: AuthenticationForm پیش‌فرض با فیلد 'username' کار می‌کند؛
    # چون USERNAME_FIELD= email است، استفاده از همون input name='username' مشکلی ندارد.


@login_required
def dashboard_view(request):
    return render(request, "accounts/dashboard.html")


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def address_list_view(request):
    addresses = request.user.addresses.order_by("-is_default", "-created_at")
    return render(request, "accounts/address_list.html", {"addresses": addresses})


@login_required
def address_create_view(request):
    form = AddressForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        addr = form.save(commit=False)
        addr.user = request.user
        addr.save()
        if addr.is_default:
            request.user.addresses.exclude(pk=addr.pk).update(is_default=False)
        messages.success(request, "Address saved.")
        return redirect("accounts:address_list")
    return render(request, "accounts/address_form.html", {"form": form})


@login_required
def address_update_view(request, pk):
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=addr, user=request.user)
    if request.method == "POST" and form.is_valid():
        addr = form.save()
        if addr.is_default:
            request.user.addresses.exclude(pk=addr.pk).update(is_default=False)
        messages.success(request, "Address updated.")
        return redirect("accounts:address_list")
    return render(request, "accounts/address_form.html", {"form": form})


@login_required
def address_delete_view(request, pk):
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        addr.delete()
        messages.success(request, "Address deleted.")
        return redirect("accounts:address_list")
    # pass as `object` to match the template
    return render(request, "accounts/address_confirm_delete.html", {"object": addr})


def activate_account_view(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except Exception:
        return HttpResponseBadRequest("Invalid activation link.")

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.email_verified = True
        user.save(update_fields=["is_active", "email_verified"])
        messages.success(request, "Your account has been activated. You can now log in.")
        return redirect("accounts:login")

    messages.error(request, "Activation link is invalid or expired.")
    return redirect("accounts:resend_activation")


@login_required
def resend_activation_view(request):
    if getattr(request.user, "email_verified", False):
        messages.info(request, "Your email is already verified.")
        return redirect("accounts:dashboard")

    current_site = get_current_site(request)
    uid = urlsafe_base64_encode(force_bytes(request.user.pk))
    token = default_token_generator.make_token(request.user)
    activation_url = reverse("accounts:activate", args=[uid, token])
    activation_link = f"{request.scheme}://{current_site.domain}{activation_url}"

    subject = render_to_string(
        "accounts/emails/activation_subject.txt", {"site_name": current_site.name}
    ).strip()
    message = render_to_string(
        "accounts/emails/activation_email.txt",
        {"user": request.user, "activation_link": activation_link, "site_name": current_site.name},
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email])
    messages.success(request, "Verification email has been re-sent.")
    return redirect("accounts:dashboard")


# Password reset (using Django auth views)
class MyPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class MyPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class MyPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class MyPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
