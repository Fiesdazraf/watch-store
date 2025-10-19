# apps/customers/views.py
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AddressForm
from .models import Address


# ---------------------------------------------------------------------
# 📍 Address list
# ---------------------------------------------------------------------
@login_required
def address_list_view(request):
    """
    Display all addresses of the current user.
    Automatically handles both Address.user and Address.customer relations.
    """
    AddressModel = apps.get_model("customers", "Address")
    if any(f.name == "user" for f in AddressModel._meta.get_fields()):
        addresses = AddressModel.objects.filter(user=request.user)
    else:
        Customer = apps.get_model("customers", "Customer")
        customer = Customer.objects.filter(user=request.user).first()
        addresses = (
            AddressModel.objects.filter(customer=customer)
            if customer
            else AddressModel.objects.none()
        )

    return render(request, "customers/address_list.html", {"addresses": addresses})


# ---------------------------------------------------------------------
# 📍 Address create
# ---------------------------------------------------------------------
@login_required
def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()

            # اگر اولین آدرس کاربر است، آن را پیش‌فرض کن
            if not Address.objects.filter(user=request.user).exclude(pk=address.pk).exists():
                address.default_shipping = True
                address.default_billing = True
                address.save(update_fields=["default_shipping", "default_billing"])

            messages.success(request, "آدرس با موفقیت ذخیره شد.")
            return redirect("customers:address_list")
    else:
        form = AddressForm()
    return render(request, "customers/address_form.html", {"form": form})


# ---------------------------------------------------------------------
# 📍 Address update
# ---------------------------------------------------------------------
@login_required
def address_update(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save(user=request.user)
            messages.success(request, "آدرس با موفقیت ویرایش شد.")
            return redirect("customers:address_list")
    else:
        form = AddressForm(
            instance=address,
            initial={
                "set_as_default_shipping": address.default_shipping,
                "set_as_default_billing": address.default_billing,
            },
        )
    return render(request, "customers/address_form.html", {"form": form, "address": address})


# ---------------------------------------------------------------------
# 📍 Address delete
# ---------------------------------------------------------------------
@login_required
def address_delete(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        address.delete()
        messages.success(request, "آدرس حذف شد.")
        return redirect("customers:address_list")
    return render(request, "customers/address_confirm_delete.html", {"address": address})


# ---------------------------------------------------------------------
# 📍 Set default
# ---------------------------------------------------------------------
@login_required
def set_default_address(request, pk: int, kind: str):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if kind == "shipping":
        Address.objects.filter(user=request.user, default_shipping=True).exclude(
            pk=address.pk
        ).update(default_shipping=False)
        address.default_shipping = True
    elif kind == "billing":
        Address.objects.filter(user=request.user, default_billing=True).exclude(
            pk=address.pk
        ).update(default_billing=False)
        address.default_billing = True
    address.save()
    messages.success(
        request, f"آدرس پیش‌فرض { 'ارسال' if kind == 'shipping' else 'صورتحساب' } تنظیم شد."
    )
    return redirect("customers:address_list")
