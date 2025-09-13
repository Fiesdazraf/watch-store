# apps/catalog/admin.py
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import Brand, Category, Collection, Product, ProductImage, ProductVariant


# -----------------------------
# Category
# -----------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("parent",)
    list_per_page = 50


# -----------------------------
# Brand
# -----------------------------
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50


# -----------------------------
# Collection
# -----------------------------
@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50


# -----------------------------
# Inlines for Product
# -----------------------------
class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = (
        "sku",
        "attribute",
        "value",
        "extra_price",
        "stock",
        "is_active",
    )  # 🔧 adjust if needed
    search_fields = ("sku", "value")
    show_change_link = True


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ("preview",)
    fields = ("image", "alt", "is_primary", "preview")

    def preview(self, obj):
        if getattr(obj, "image", None):
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px;object-fit:cover"/>',
                obj.image.url,
            )
        return "-"

    preview.short_description = "Preview"


# -----------------------------
# Helpers / Filters
# -----------------------------
class LowStockFilter(admin.SimpleListFilter):
    title = "Low stock"
    parameter_name = "low_stock"

    def lookups(self, request, model_admin):
        return [
            ("zero", "Out of stock (=0)"),
            ("lt5", "< 5"),
            ("lt10", "< 10"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "zero":
            return queryset.filter(stock__lte=0)
        if self.value() == "lt5":
            return queryset.filter(stock__lt=5)
        if self.value() == "lt10":
            return queryset.filter(stock__lt=10)
        return queryset


# -----------------------------
# ProductVariant
# -----------------------------
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "product",
        "price_final",
        "stock_badge",
        "is_active",
    )  # 🔧 adjust if needed
    search_fields = ("sku", "product__title", "product__brand__name")
    list_select_related = ("product", "product__brand")
    list_filter = (
        LowStockFilter,
        "is_active",
        "product__brand",
    )  # 🔧 adjust brand field name if needed
    autocomplete_fields = ("product",)
    ordering = ("-is_active", "stock", "sku")
    list_per_page = 50
    actions = ["make_active", "make_inactive"]

    def price_final(self, obj):
        # product.price + extra_price (if both exist)
        base = getattr(obj.product, "price", 0) or 0
        extra = getattr(obj, "extra_price", 0) or 0
        return f"{base + extra:,.0f}"

    price_final.short_description = "Final Price"

    def stock_badge(self, obj):
        stock = getattr(obj, "stock", None)
        if stock is None:
            return "-"
        if stock <= 0:
            color = "#e74c3c"  # red
        elif stock < 5:
            color = "#f39c12"  # orange
        else:
            color = "#27ae60"  # green
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, stock)

    stock_badge.short_description = "Stock"

    @admin.action(description="Mark selected variants as Active")
    def make_active(self, request, queryset):
        if "is_active" in [f.name for f in ProductVariant._meta.fields]:
            updated = queryset.update(is_active=True)
            self.message_user(request, f"{updated} variants marked active.")

    @admin.action(description="Mark selected variants as Inactive")
    def make_inactive(self, request, queryset):
        if "is_active" in [f.name for f in ProductVariant._meta.fields]:
            updated = queryset.update(is_active=False)
            self.message_user(request, f"{updated} variants marked inactive.")


# -----------------------------
# Product
# -----------------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "thumb",
        "title",
        "brand",
        "price",
        "variants_count",
        "is_active",
    )  # 🔧 adjust fields if needed
    search_fields = ("title", "brand__name")
    list_select_related = ("brand",)
    list_filter = ("is_active", "brand")  # می‌تونی brand__category اضافه کنی اگر فیلدش هست
    inlines = [ProductVariantInline, ProductImageInline]
    autocomplete_fields = ("brand",)  # 🔧 اگر فیلد ForeignKey هست
    save_on_top = True
    list_per_page = 25
    actions = ["make_active", "make_inactive"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # annotate variants count برای نمایش سریع
        return qs.annotate(
            _variants_count=Count("variants")
        )  # 🔧 adjust related_name if not "variants"

    def thumb(self, obj):
        # primary image or first image
        primary = (
            obj.images.filter(is_primary=True).first() or obj.images.first()
        )  # 🔧 adjust related_name if not "images"
        if primary and getattr(primary, "image", None):
            return format_html(
                '<img src="{}" style="height:48px;width:48px;'
                'border-radius:6px;object-fit:cover" />',
                primary.image.url,
            )
        return "-"

    thumb.short_description = "Image"

    def variants_count(self, obj):
        # uses annotated value; fallback to related count
        val = getattr(obj, "_variants_count", None)
        if val is None:
            val = obj.variants.count()  # 🔧 adjust related_name if needed
        color = "#999"
        if val == 0:
            color = "#e74c3c"
        elif val < 3:
            color = "#f39c12"
        else:
            color = "#27ae60"
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, val)

    variants_count.short_description = "Variants"

    @admin.action(description="Mark selected products as Active")
    def make_active(self, request, queryset):
        if "is_active" in [f.name for f in Product._meta.fields]:
            updated = queryset.update(is_active=True)
            self.message_user(request, f"{updated} products marked active.")

    @admin.action(description="Mark selected products as Inactive")
    def make_inactive(self, request, queryset):
        if "is_active" in [f.name for f in Product._meta.fields]:
            updated = queryset.update(is_active=False)
            self.message_user(request, f"{updated} products marked inactive.")
