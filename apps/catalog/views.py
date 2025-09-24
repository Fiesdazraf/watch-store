# apps/catalog/views.py
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Sum
from django.shortcuts import render
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
            .prefetch_related("images", "variants")
            .only(
                "id",
                "slug",
                "title",
                "price",
                "brand_id",
                "category_id",
                "collection_id",
            )
            .filter(is_active=True)
        )

        q = (self.request.GET.get("q") or "").strip()
        brand = (self.request.GET.get("brand") or "").strip()
        cat = (self.request.GET.get("category") or "").strip()
        pmin = (self.request.GET.get("price_min") or "").strip()
        pmax = (self.request.GET.get("price_max") or "").strip()
        order = (self.request.GET.get("order") or "newest").strip()

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
        if pmin_dec is not None and pmax_dec is not None and pmin_dec > pmax_dec:
            pmin_dec, pmax_dec = pmax_dec, pmin_dec

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

        # brands cache
        brands = cache.get("catalog:brands:ordered")
        if brands is None:
            brands_qs = Brand.objects.only("id", "name", "slug").order_by("name")
            brands = list(brands_qs)
            cache.set("catalog:brands:ordered", brands, 60 * 10)

        # categories cache
        categories = cache.get("catalog:categories:ordered")
        if categories is None:
            categories_qs = Category.objects.only("id", "name", "slug").order_by("name")
            categories = list(categories_qs)
            cache.set("catalog:categories:ordered", categories, 60 * 10)

        ctx["brands"] = list(brands)
        ctx["categories"] = list(categories)

        # sticky filters for template
        ctx["applied_filters"] = {
            "q": (self.request.GET.get("q") or "").strip(),
            "brand": (self.request.GET.get("brand") or "").strip(),
            "category": (self.request.GET.get("category") or "").strip(),
            "price_min": (self.request.GET.get("price_min") or "").strip(),
            "price_max": (self.request.GET.get("price_max") or "").strip(),
            "order": (self.request.GET.get("order") or "newest").strip(),
        }

        # build querystring WITHOUT page param (useful for pagination links)
        qs = self.request.GET.copy()
        qs.pop("page", None)
        ctx["querystring"] = qs.urlencode()

        return ctx

    def get(self, request, *args, **kwargs):
        """
        Support HTMX requests: when HTMX calls the view (HX-Request header present),
        return only the products grid partial so front-end can swap it in place.
        Otherwise return full template as normal.
        """
        response = super().get(request, *args, **kwargs)
        is_hx = request.headers.get("HX-Request") == "true"
        if is_hx:
            # use the same context as full view but render only partial grid
            context = response.context_data
            return render(request, "catalog/_products_grid.html", context)
        return response


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
                "short_description",
                "price",
                "discounted_price",
                "is_active",
                "brand__name",
                "brand__slug",
                "category__name",
                "category__slug",
                "collection__name",
            )
            .filter(is_active=True)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        product = self.object

        # مجموع موجودی (اگر واریانت داری)
        total_stock = None
        if hasattr(product, "variants"):
            agg = product.variants.aggregate(total=Sum("stock"))
            total_stock = agg.get("total") or 0

        # related products: same category (exclude self), fallback to same brand
        related = Product.objects.filter(is_active=True).exclude(pk=product.pk)
        if product.category_id:
            related = related.filter(category_id=product.category_id)
        else:
            related = related.filter(brand_id=product.brand_id)
        ctx["related_products"] = related.select_related("brand").prefetch_related("images")[:4]

        ctx["total_stock"] = total_stock
        ctx["has_variants"] = product.variants.exists() if hasattr(product, "variants") else False
        return ctx
