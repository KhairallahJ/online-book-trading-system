"""The shopping cart's public interface.

Checkout (orders.services) and the views work with carts through these functions and plain IDs / value
objects instead of reaching into the cart models and chaining their querysets.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from .models import Cart, CartItem


class CartError(Exception):
    """A cart change that can't be made, e.g. asking for more copies than are in stock."""


@dataclass(frozen=True)
class CartLine:
    book_id: int
    title: str
    unit_price: Decimal
    quantity: int

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


def book_model():
    """The catalogue's Book model, resolved through the FK rather than imported from another app."""
    return CartItem._meta.get_field('book').related_model


def get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def item_count(user):
    return CartItem.objects.filter(cart__user=user).aggregate(total=Sum('quantity'))['total'] or 0


def _check_stock(book, quantity):
    if quantity > book.stock:
        available = 'none' if book.stock == 0 else f'only {book.stock}'
        raise CartError(f'Sorry, {available} left of "{book.title}".')


def add_book(cart, book, quantity=1):
    if book.posted_by_id == cart.user_id:
        raise CartError("You can't buy your own listing.")
    item = CartItem.objects.filter(cart=cart, book=book).first()
    new_quantity = (item.quantity if item else 0) + quantity
    _check_stock(book, new_quantity)
    if item:
        item.quantity = new_quantity
        item.save(update_fields=['quantity'])
    else:
        item = CartItem.objects.create(cart=cart, book=book, quantity=quantity)
    return item


def set_quantity(item, quantity):
    """Change a line's quantity; zero removes the line."""
    if quantity <= 0:
        item.delete()
        return None
    _check_stock(item.book, quantity)
    item.quantity = quantity
    item.save(update_fields=['quantity'])
    return item


def get_cart_lines(cart_id):
    """Snapshot of a cart's contents as plain values, priced at the current catalogue price."""
    items = CartItem.objects.filter(cart_id=cart_id).select_related('book')
    return [
        CartLine(book_id=item.book_id, title=item.book.title, unit_price=item.book.price, quantity=item.quantity)
        for item in items
    ]


def clear_cart(cart_id):
    CartItem.objects.filter(cart_id=cart_id).delete()
