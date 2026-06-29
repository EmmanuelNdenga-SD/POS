from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=100 , unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    last_restocked = models.DateTimeField(default=timezone.now)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Retail Price")
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Wholesale Price", default=0.00)
    quantity_in_stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (Stock: {self.quantity_in_stock})"

class Sale(models.Model):
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
    )
    PAYMENT_STATUS = (
        ('paid', 'Paid'),
        ('pending', 'Pending'),  # for credit sales
    )
    customer_name = models.CharField(max_length=100, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='paid')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale #{self.id} - {self.created_at.date()}"

class SaleItem(models.Model):
    PRICE_TYPE_CHOICES = (
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
    )
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    price_type = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES, default='retail')

    def __str__(self):
        return f"{self.product.name} x {self.quantity} ({self.get_price_type_display()})"

    def save(self, *args, **kwargs):
        # Deduct stock if the sale is marked as 'paid'
        if self.sale.payment_status == 'paid':
            product = self.product
            if product.quantity_in_stock < self.quantity:
                raise ValueError(f"Insufficient stock for {product.name}")
            product.quantity_in_stock -= self.quantity
            product.save()
        super().save(*args, **kwargs)
        
        

class DeletionRequest(models.Model):
    OBJECT_TYPES = (
        ('product', 'Product'),
        ('sale', 'Sale'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    object_type = models.CharField(max_length=20, choices=OBJECT_TYPES)
    object_id = models.PositiveIntegerField()
    object_repr = models.CharField(max_length=200)  # e.g., product name or "Sale #123"
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deletion_requests')
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_requests')
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"Delete {self.object_type} #{self.object_id} ({self.object_repr}) by {self.requested_by.username}"