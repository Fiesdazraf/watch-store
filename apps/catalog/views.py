from decimal import Decimal
from django.views.generic import ListView, DetailView
from django.db.models import Q
from .models import Product, Brand, Category


class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = Product.objects.select_related("brand", "collection", "category").filter(
            is_active=True
        )

        # --- Read filters
        q = self.request.GET.get("q")
        brand = self.request.GET.get("brand")
        cat = self.request.GET.get("category")
        pmin = self.request.GET.get("price_min")
        pmax = self.request.GET.get("price_max")
        order = self.request.GET.get("order", "newest")  # default

        # --- Apply text/choice filters
        if q:
            qs = qs.filter(
                Q(title__icontains=q) | Q(sku__icontains=q) | Q(brand__name__icontains=q)
            )
        if brand:
            qs = qs.filter(brand__slug=brand)
        if cat:
            qs = qs.filter(category__slug=cat)

        # --- Validate numeric filters safely
        def to_decimal(x):
            try:
                return Decimal(x)
            except Exception:
                return None

        pmin_dec = to_decimal(pmin)
        pmax_dec = to_decimal(pmax)

        if pmin_dec is not None:
            qs = qs.filter(price__gte=pmin_dec)
        if pmax_dec is not None:
            qs = qs.filter(price__lte=pmax_dec)

        # --- Safe ordering via whitelist
        allowed_orders = {
            "price_asc": "price",
            "price_desc": "-price",
            "newest": "-created_at",
        }
        qs = qs.order_by(allowed_orders.get(order, "-created_at"))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["brands"] = Brand.objects.order_by("name")
        ctx["categories"] = Category.objects.order_by("name")
        return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "catalog/product_detail.html"
    context_object_name = "product"
