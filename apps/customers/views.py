# apps/customers/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AddressForm
from .models import Address


@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, "customers/address_list.html", {"addresses": addresses})


@login_required
def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)  # ذخیره موقت بدون ثبت در DB
            address.user = request.user  # نسبت دادن کاربر فعلی
            address.save()  # حالا در DB ذخیره کن
        if not Address.objects.filter(user=request.user).exclude(pk=address.pk).exists():
            address.default_shipping = True
            address.default_billing = True
            address.save(update_fields=["default_shipping", "default_billing"])

            messages.success(request, "آدرس با موفقیت ذخیره شد.")
            return redirect("customers:address_list")
    else:
        form = AddressForm()

    return render(request, "customers/address_form.html", {"form": form})


@login_required
def address_update(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save(user=request.user)
            messages.success(request, "Address updated.")
            return redirect("customers:address_list")
    else:
        # Prefill default toggles
        form = AddressForm(
            instance=address,
            initial={
                "set_as_default_shipping": address.default_shipping,
                "set_as_default_billing": address.default_billing,
            },
        )
    return render(request, "customers/address_form.html", {"form": form, "address": address})


@login_required
def address_delete(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        address.delete()
        messages.success(request, "Address deleted.")
        return redirect("customers:address_list")
    return render(request, "customers/address_confirm_delete.html", {"address": address})


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
    messages.success(request, f"Default {kind} address set.")
    return redirect("customers:address_list")
