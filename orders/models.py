from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Cart(models.Model):
    """A signed-in customer's shopping cart (one per user)."""

    user       = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user}"

    @property
    def total(self):
        return sum((item.subtotal for item in self.items.all()), Decimal('0.00'))

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart     = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    # Referenced by app label, and without a reverse accessor, so the catalog stays unaware of carts.
    book     = models.ForeignKey('catalog.Book', on_delete=models.CASCADE, related_name='+')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['added_at', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['cart', 'book'], name='unique_book_per_cart'),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.book}"

    @property
    def subtotal(self):
        return self.book.price * self.quantity


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = 'placed', 'Placed'
        SHIPPED = 'shipped', 'Shipped'
        CANCELLED = 'cancelled', 'Cancelled'

    user             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    status           = models.CharField(max_length=10, choices=Status.choices, default=Status.PLACED)
    full_name        = models.CharField(max_length=150)
    email            = models.EmailField()
    shipping_address = models.TextField()
    # Stored rather than computed so the order keeps the amount actually charged.
    total            = models.DecimalField(max_digits=10, decimal_places=2)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['user', '-created_at'], name='order_user_recent_idx')]

    def __str__(self):
        return f"Order {self.number}"

    def get_absolute_url(self):
        return reverse('orders:detail', args=[self.pk])

    @property
    def number(self):
        return f"BTS-{self.pk:06d}"

    @property
    def can_cancel(self):
        return self.status == self.Status.PLACED


class OrderItem(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    # SET_NULL keeps order history if a book is later removed from the catalogue;
    # title and price are copied so the order still reads correctly.
    book       = models.ForeignKey('catalog.Book', on_delete=models.SET_NULL, null=True, related_name='+')
    title      = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity   = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    def __str__(self):
        return f"{self.quantity} × {self.title}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity
