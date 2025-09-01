from django.db import models
from django.utils.text import slugify
from django.db.models import UniqueConstraint


class Category(models.Model):
    """
    Hierarchical category (e.g. Men > Luxury > Rolex, or Unisex > Entry-level).
    """

    name = models.CharField(
        max_length=120
    )  # no global unique (allow same name under different parents)
    slug = models.SlugField(
        max_length=140, blank=True
    )  # uniqueness handled via UniqueConstraint below
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

    def __str__(self):
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

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


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

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    Minimal product for MVP, now linked to hierarchical Category.
    """

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        help_text="Attach product to the most specific category node (optional).",
    )

    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # base currency
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["category"]),
            models.Index(fields=["sku"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    """
    A simple variant model to represent options like strap/color/size, each with its own SKU/stock.
    """

    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    sku = models.CharField(max_length=40, unique=True)
    attribute = models.CharField(max_length=60)  # e.g. "strap", "color", "size"
    is_active = models.BooleanField(default=True)
    value = models.CharField(max_length=60)  # e.g. "leather - brown", "blue", "42mm"
    extra_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
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

    def __str__(self):
        return f"{self.product.title} - {self.attribute}: {self.value}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/")
    alt = models.CharField(max_length=160, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "id"]
