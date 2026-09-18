from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Author, Book, Genre
from orders import cart as services
from orders.models import Cart, CartItem


class CartTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user('seller')
        genre = Genre.objects.create(name='Fantasy')
        author = Author.objects.create(name='Ursula K. Le Guin')
        cls.book = Book.objects.create(
            title='A Wizard of Earthsea', author=author, genre=genre, isbn='9780141354300',
            price=Decimal('9.50'), stock=3, posted_by=cls.seller,
        )
        cls.other_book = Book.objects.create(
            title='The Left Hand of Darkness', author=author, genre=genre, isbn='9780441478125',
            price=Decimal('11.00'), stock=1, posted_by=cls.seller,
        )
        cls.user = User.objects.create_user('reader')

    def setUp(self):
        self.client.force_login(self.user)

    def add(self, book, quantity=1):
        return self.client.post(reverse('orders:cart_add', args=[book.id]), {'quantity': quantity})

    def cart_item(self, book):
        return CartItem.objects.get(cart__user=self.user, book=book)


class AddToCartTests(CartTestCase):
    def test_adding_creates_the_cart_and_line(self):
        response = self.add(self.book, 2)

        self.assertRedirects(response, reverse('orders:cart'))
        self.assertEqual(self.cart_item(self.book).quantity, 2)

    def test_adding_again_increases_quantity(self):
        self.add(self.book)
        self.add(self.book)

        self.assertEqual(self.cart_item(self.book).quantity, 2)
        self.assertEqual(Cart.objects.count(), 1)

    def test_cannot_add_more_than_stock(self):
        self.add(self.book, 2)

        response = self.add(self.book, 2)

        self.assertRedirects(response, self.book.get_absolute_url())
        self.assertEqual(self.cart_item(self.book).quantity, 2)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertEqual(messages[-1], 'Sorry, only 3 left of "A Wizard of Earthsea".')

    def test_adding_does_not_change_stock(self):
        self.add(self.book, 2)

        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 3)

    def test_cannot_buy_own_listing(self):
        self.client.force_login(self.seller)

        response = self.add(self.book)

        self.assertRedirects(response, self.book.get_absolute_url())
        self.assertFalse(CartItem.objects.exists())
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertEqual(messages[-1], "You can't buy your own listing.")

    def test_invalid_quantity_is_rejected(self):
        self.add(self.book, 0)

        self.assertFalse(CartItem.objects.exists())

    def test_requires_post(self):
        response = self.client.get(reverse('orders:cart_add', args=[self.book.id]))

        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        self.client.logout()

        response = self.add(self.book)

        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('orders:cart_add', args=[self.book.id])}",
                             fetch_redirect_response=False)
        self.assertFalse(CartItem.objects.exists())

    def test_unknown_book_is_404(self):
        response = self.client.post(reverse('orders:cart_add', args=[9999]), {'quantity': 1})

        self.assertEqual(response.status_code, 404)


@override_settings(CURRENCY_SYMBOL='€')
class ManageCartTests(CartTestCase):
    def setUp(self):
        super().setUp()
        self.add(self.book, 1)
        self.item = self.cart_item(self.book)

    def update(self, quantity, item=None):
        return self.client.post(reverse('orders:cart_update', args=[(item or self.item).id]), {'quantity': quantity})

    def test_update_quantity(self):
        self.update(3)

        self.assertEqual(self.cart_item(self.book).quantity, 3)

    def test_update_to_zero_removes_the_line(self):
        self.update(0)

        self.assertFalse(CartItem.objects.exists())

    def test_update_above_stock_is_rejected(self):
        self.update(4)

        self.assertEqual(self.cart_item(self.book).quantity, 1)

    def test_remove(self):
        self.client.post(reverse('orders:cart_remove', args=[self.item.id]))

        self.assertFalse(CartItem.objects.exists())

    def test_cannot_touch_another_users_cart(self):
        intruder = get_user_model().objects.create_user('intruder')
        self.client.force_login(intruder)

        self.assertEqual(self.update(2).status_code, 404)
        self.assertEqual(self.client.post(reverse('orders:cart_remove', args=[self.item.id])).status_code, 404)
        self.assertEqual(self.cart_item(self.book).quantity, 1)

    def test_cart_page_shows_lines_total_and_nav_count(self):
        self.add(self.other_book, 1)

        response = self.client.get(reverse('orders:cart'))

        self.assertContains(response, 'A Wizard of Earthsea')
        self.assertContains(response, '€20.50')  # 9.50 + 11.00
        self.assertEqual(response.context['cart_item_count'], 2)


class CartServiceTests(CartTestCase):
    def test_cart_lines_are_plain_value_snapshots(self):
        cart = services.get_cart(self.user)
        services.add_book(cart, self.book, 2)

        [line] = services.get_cart_lines(cart.id)

        self.assertEqual(line, services.CartLine(self.book.id, 'A Wizard of Earthsea', Decimal('9.50'), 2))
        self.assertEqual(line.subtotal, Decimal('19.00'))

    def test_clear_cart(self):
        cart = services.get_cart(self.user)
        services.add_book(cart, self.book)

        services.clear_cart(cart.id)

        self.assertEqual(services.get_cart_lines(cart.id), [])
