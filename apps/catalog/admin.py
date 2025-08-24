from django.contrib import admin
from .models import Brand, Collection, Product

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "collection", "price", "is_active", "created_at")
    list_filter = ("brand", "collection", "is_active")
    search_fields = ("title", "sku")
    prepopulated_fields = {"slug": ("title",)}
