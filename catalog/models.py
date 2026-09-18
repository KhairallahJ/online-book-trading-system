from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=200)
    bio = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('catalog:author_detail', args=[self.pk])


isbn_validator = RegexValidator(
    r'^(\d{9}[\dX]|\d{13})$', 'Enter a 10- or 13-digit ISBN without spaces or hyphens.'
)


class Book(models.Model):
    """A member's listing of a physical book, available to buy and optionally to swap."""

    class Condition(models.TextChoices):
        NEW = 'new', 'New'
        LIKE_NEW = 'like_new', 'Like new'
        GOOD = 'good', 'Good'
        FAIR = 'fair', 'Fair'

    title         = models.CharField(max_length=200)
    # Not unique: several members can list their own copy of the same edition.
    isbn          = models.CharField('ISBN', max_length=13, db_index=True, validators=[isbn_validator])
    # PROTECT: removing an author or genre must not silently delete listings.
    author        = models.ForeignKey(Author, on_delete=models.PROTECT, related_name='books')
    condition     = models.CharField(max_length=10, choices=Condition.choices, default=Condition.GOOD)
    price         = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    genre         = models.ForeignKey(Genre, on_delete=models.PROTECT, related_name='books')
    posted_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='listings')
    stock         = models.PositiveIntegerField('copies available', default=1)
    open_to_trade = models.BooleanField(
        default=True, help_text='Show this book in the trading area so other members can offer a swap.'
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.title} by {self.author}"

    def get_absolute_url(self):
        return reverse('catalog:book_detail', args=[self.pk])

    @property
    def in_stock(self):
        return self.stock > 0

    def can_edit(self, user):
        return user.is_authenticated and (user.is_staff or user.pk == self.posted_by_id)
