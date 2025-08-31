from django.contrib import admin
from .models import Category, Brand, Collection, Product, ProductVariant, ProductImage


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
    extra = 1
    fields = ("image", "alt", "is_primary")
    readonly_fields = ("is_primary",)


# -----------------------------
# Product
# -----------------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "brand",
        "collection",
        "category",
        "price",
        "is_active",
        "created_at",
    )
    list_filter = ("brand", "collection", "category", "is_active")
    search_fields = ("title", "sku")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductVariantInline, ProductImageInline]
