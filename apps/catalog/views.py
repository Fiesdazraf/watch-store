from django.views.generic import ListView, DetailView
from django.db.models import Q
from .models import Product, Brand, Category

class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = Product.objects.select_related("brand", "collection", "category").filter(is_active=True)
        q = self.request.GET.get("q")
        brand = self.request.GET.get("brand")
        cat = self.request.GET.get("category")
        pmin = self.request.GET.get("price_min")
        pmax = self.request.GET.get("price_max")
        order = self.request.GET.get("order")

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(sku__icontains=q) | Q(brand__name__icontains=q))
        if brand:
            qs = qs.filter(brand__slug=brand)
        if cat:
            qs = qs.filter(category__slug=cat)
        if pmin:
            qs = qs.filter(price__gte=pmin)
        if pmax:
            qs = qs.filter(price__lte=pmax)

        if order == "price_asc":
            qs = qs.order_by("price")
        elif order == "price_desc":
            qs = qs.order_by("-price")
        else:
            qs = qs.order_by("-created_at")
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
