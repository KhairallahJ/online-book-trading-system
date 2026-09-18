from django.db import transaction
from django.db.models import F

from . import cart as cart_services
from .models import Order, OrderItem


class CheckoutError(Exception):
    """The order can't be placed or changed, e.g. the cart is empty or stock ran out."""


def book_model():
    """The catalogue's Book model, resolved through the FK rather than imported from another app."""
    return OrderItem._meta.get_field('book').related_model


@transaction.atomic
def place_order(user, *, full_name, email, shipping_address):
    """Turn the user's cart into an order: re-check and decrement stock, record the items, empty the cart."""
    cart = cart_services.get_cart(user)
    lines = cart_services.get_cart_lines(cart.id)
    if not lines:
        raise CheckoutError('Your cart is empty.')

    Book = book_model()
    # Lock the rows so two customers can't buy the last copy at the same time.
    books = Book.objects.select_for_update().in_bulk([line.book_id for line in lines])
    for line in lines:
        book = books.get(line.book_id)
        if book is None or book.stock < line.quantity:
            raise CheckoutError(f'Sorry, "{line.title}" no longer has {line.quantity} in stock.')

    order = Order.objects.create(
        user=user,
        full_name=full_name,
        email=email,
        shipping_address=shipping_address,
        total=sum(line.subtotal for line in lines),
    )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order, book_id=line.book_id, title=line.title, unit_price=line.unit_price, quantity=line.quantity
        )
        for line in lines
    ])
    for line in lines:
        Book.objects.filter(pk=line.book_id).update(stock=F('stock') - line.quantity)

    cart_services.clear_cart(cart.id)
    return order


@transaction.atomic
def cancel_order(order):
    """Cancel an order that hasn't shipped and put its books back in stock."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_cancel:
        raise CheckoutError(f'Order {order.number} has already been {order.get_status_display().lower()}.')
    Book = book_model()
    for item in order.items.exclude(book=None):
        Book.objects.filter(pk=item.book_id).update(stock=F('stock') + item.quantity)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    return order
