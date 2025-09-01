from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from .forms import RegisterForm, ProfileForm, AddressForm
from .models import Address

User = get_user_model()

def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/register.html", {"form": form})

class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

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
    form = AddressForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        addr = form.save(commit=False)
        addr.user = request.user
        addr.save()
        # فقط یکی default باشد
        if addr.is_default:
            request.user.addresses.exclude(pk=addr.pk).update(is_default=False)
        messages.success(request, "Address saved.")
        return redirect("accounts:address_list")
    return render(request, "accounts/address_form.html", {"form": form})

@login_required
def address_update_view(request, pk):
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=addr)
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
    return render(request, "accounts/address_confirm_delete.html", {"address": addr})

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
