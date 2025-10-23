# apps/catalog/models.py
from __future__ import annotations

from functools import cached_property

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.text import slugify


# -----------------------------------------------------------------------------
# Category
# -----------------------------------------------------------------------------
class Category(models.Model):
    """
    Hierarchical category (e.g. Men > Luxury > Rolex, or Unisex > Entry-level).
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)  # per-parent uniqueness via constraint
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        help_text="Parent category for nesting (leave empty for a root category).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["parent"]),
        ]
        constraints = [
            UniqueConstraint(fields=["parent", "name"], name="uniq_category_name_per_parent"),
            UniqueConstraint(fields=["parent", "slug"], name="uniq_category_slug_per_parent"),
            models.CheckConstraint(
                check=~models.Q(id=models.F("parent")), name="category_parent_not_self"
            ),
        ]

    def __str__(self) -> str:
        # Show full path like: Men > Luxury > Rolex
        parts = [self.name]
        p = self.parent
        while p:
            parts.append(p.name)
            p = p.parent
        return " > ".join(reversed(parts))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Brand
# -----------------------------------------------------------------------------
class Brand(models.Model):
    """
    Watch brand (e.g., Seiko, Omega, Rolex).
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    # Optional: attach a brand to a category node (e.g., Men > Luxury)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brands",
        help_text="Optional: place brand under a specific category node.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["slug"])]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Collection
# -----------------------------------------------------------------------------
class Collection(models.Model):
    """
    Product grouping/line (e.g., Diver, Dress, Chronograph).
    """

    name = models.CharField(max_length=140, unique=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    # Optional: collections can also live under a category (e.g., Men > Sport)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collections",
        help_text="Optional: place collection under a specific category node.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["slug"])]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# ProductImage  (زودتر می‌آد تا QuerySet بتونه Prefetch بسازه)
# -----------------------------------------------------------------------------
class ProductImage(models.Model):
    product = models.ForeignKey("Product", related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/")
    alt = models.CharField(max_length=160, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "id"]
        constraints = [
            # ensure only one primary image per product
            UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="uniq_primary_image_per_product",
            )
        ]

    def __str__(self) -> str:
        return f"Image #{self.pk} for {self.product_id}"


# -----------------------------------------------------------------------------
# ProductQuerySet / ProductManager  (قبل از Product)
# -----------------------------------------------------------------------------
class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_list(self):
        # Lightweight prefetch for listing cards
        return (
            self.active()
            .select_related("brand", "category", "collection")
            .prefetch_related(
                models.Prefetch(
                    "images",
                    queryset=ProductImage.objects.only(
                        "id", "image", "is_primary", "product_id"
                    ).order_by("-is_primary", "id"),
                ),
                "variants",
            )
        )

    def for_detail(self):
        # Richer prefetch for PDP
        return (
            self.active()
            .select_related("brand", "category", "collection")
            .prefetch_related(
                models.Prefetch(
                    "images",
                    queryset=ProductImage.objects.only(
                        "id", "image", "alt", "is_primary", "product_id"
                    ).order_by("-is_primary", "id"),
                ),
                "variants",
            )
        )


class ProductManager(models.Manager):
    def get_queryset(self):
        return ProductQuerySet(self.model, using=self._db)

    # sugar methods
    def active(self):
        return self.get_queryset().active()

    def for_list(self):
        return self.get_queryset().for_list()

    def for_detail(self):
        return self.get_queryset().for_detail()


# -----------------------------------------------------------------------------
# Product
# -----------------------------------------------------------------------------
class Product(models.Model):
    """
    Minimal product for MVP, linked to hierarchical Category.
    """

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, db_index=True, blank=True)

    brand = models.ForeignKey(
        "Brand", on_delete=models.PROTECT, related_name="products", db_index=True
    )
    collection = models.ForeignKey(
        "Collection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    category = models.ForeignKey(
        "Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        help_text="Attach product to the most specific category node (optional).",
        db_index=True,
    )

    objects = ProductManager()

    short_description = models.CharField(max_length=300, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    discounted_price = models.DecimalField(max_digits=12, decimal_places=0, blank=True, null=True)

    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    is_active = models.BooleanField(default=True)

    # ✅ فیلد جدید برای محصولات ویژه
    is_featured = models.BooleanField(
        default=False,
        help_text=(
            "Mark this product as featured "
            "to display it on the homepage or highlighted sections."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["category"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["is_active", "brand"]),
            models.Index(fields=["is_active", "category"]),
            # ✅ ایندکس جدید برای نمایش سریع‌تر featured products
            models.Index(fields=["is_active", "is_featured"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @cached_property
    def primary_image(self) -> ProductImage | None:
        """
        Returns the primary image if available; otherwise the first prefetched image.
        Works best when images are prefetch_related.
        """
        imgs = list(getattr(self, "images").all())
        for im in imgs:
            if getattr(im, "is_primary", False):
                return im.image
        return imgs[0].image if imgs else None


# -----------------------------------------------------------------------------
# ProductVariant
# -----------------------------------------------------------------------------
class ProductVariant(models.Model):
    """
    A simple variant model to represent options like strap/color/size, each with its own SKU/stock.
    """

    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    sku = models.CharField(max_length=40, unique=True)
    attribute = models.CharField(max_length=60)  # e.g. "strap", "color", "size"
    is_active = models.BooleanField(default=True)
    value = models.CharField(max_length=60)  # e.g. "leather - brown", "blue", "42mm"
    extra_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Product Variant"
        verbose_name_plural = "Product Variants"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute", "value"],
                name="uniq_variant_attr_value_per_product",
            )
        ]
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.title} - {self.attribute}: {self.value}"
