from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q
from django.views.generic import DetailView, ListView

from .models import Brand, Category, Product


class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Product.objects.select_related("brand", "collection", "category")
            .prefetch_related(
                "images",  # if you show images in product cards
                "variants",  # if you show variants info in list
            )
            .only(
                "id",
                "slug",
                "title",
                "price",
                "brand__name",
                "brand__slug",
                "category__name",
                "category__slug",
                "collection__name",
            )
            .filter(is_active=True)
        )

        q = self.request.GET.get("q")
        brand = self.request.GET.get("brand")
        cat = self.request.GET.get("category")
        pmin = self.request.GET.get("price_min")
        pmax = self.request.GET.get("price_max")
        order = self.request.GET.get("order", "newest")

        if q:
            qs = qs.filter(
                Q(title__icontains=q) | Q(sku__icontains=q) | Q(brand__name__icontains=q)
            )
        if brand:
            qs = qs.filter(brand__slug=brand)
        if cat:
            qs = qs.filter(category__slug=cat)

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

        allowed_orders = {
            "price_asc": "price",
            "price_desc": "-price",
            "newest": "-created_at",
        }
        return qs.order_by(allowed_orders.get(order, "-created_at"))


def get_context_data(self, **kwargs):
    ctx = super().get_context_data(**kwargs)

    brands = cache.get("catalog_brands_ordered")
    if brands is None:
        brands_qs = Brand.objects.only("id", "name", "slug").order_by("name")
        brands = list(brands_qs)
        cache.set("catalog_brands_ordered", brands, 60 * 10)  # 10 minutes

    categories = cache.get("catalog_categories_ordered")
    if categories is None:
        categories_qs = Category.objects.only("id", "name", "slug").order_by("name")
        categories = list(categories_qs)
        cache.set("catalog_categories_ordered", categories, 60 * 10)  # 10 minutes

    # ✅ همیشه list باشند تا رفتار پایدار بماند
    ctx["brands"] = list(brands)
    ctx["categories"] = list(categories)
    return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return (
            Product.objects.select_related("brand", "collection", "category")
            .prefetch_related("images", "variants")
            .only(
                "id",
                "slug",
                "title",
                "description",
                "price",
                "brand__name",
                "brand__slug",
                "category__name",
                "category__slug",
                "collection__name",
            )
            .filter(is_active=True)
        )
