from django.contrib import admin
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


# -----------------------------
# Brand
# -----------------------------
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


# -----------------------------
# Collection
# -----------------------------
@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


# -----------------------------
# Product inlines (variants + images)
# -----------------------------
class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("sku", "attribute", "value", "extra_price", "stock")
    search_fields = ("sku", "value")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ("preview",)
    fields = ("image", "alt", "is_primary", "preview")

    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px"/>', obj.image.url
            )
        return "-"

    preview.short_description = "Preview"


# -----------------------------
# Product
# -----------------------------
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "extra_price", "stock", "is_active")
    search_fields = ("sku", "product__title", "product__brand__name")
    list_select_related = ("product", "product__brand")
    list_filter = ("is_active", "product__brand")
    autocomplete_fields = ("product",)  # سریع‌تر برای دیتابیس بزرگ


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "price", "is_active")
    search_fields = ("title", "brand__name")
    list_select_related = ("brand",)
    list_filter = ("is_active", "brand")
    inlines = [ProductVariantInline, ProductImageInline]
