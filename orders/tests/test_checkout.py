from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Author, Book, Genre
from orders import cart as cart_services
from orders import services
from orders.models import Order, OrderItem

SHIPPING = {
    'full_name': 'Aoife Byrne',
    'email': 'aoife@example.com',
    'shipping_address': '12 Main Street\nDublin 9',
}


class OrdersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        seller = User.objects.create_user('seller')
        genre = Genre.objects.create(name='Mystery')
        author = Author.objects.create(name='Agatha Christie')
        cls.orient = Book.objects.create(
            title='Murder on the Orient Express', author=author, genre=genre, isbn='9780007119318',
            price=Decimal('8.99'), stock=2, posted_by=seller,
        )
        cls.none_left = Book.objects.create(
            title='And Then There Were None', author=author, genre=genre, isbn='9780007136834',
            price=Decimal('7.50'), stock=5, posted_by=seller,
        )
        cls.user = User.objects.create_user('buyer', email='buyer@example.com', first_name='Aoife', last_name='Byrne')
        cls.staff = User.objects.create_superuser('boss', 'boss@example.com', 'unused')

    def setUp(self):
        self.client.force_login(self.user)
        self.cart = cart_services.get_cart(self.user)

    def fill_cart(self):
        cart_services.add_book(self.cart, self.orient, 2)
        cart_services.add_book(self.cart, self.none_left, 1)

    def refresh_stock(self):
        self.orient.refresh_from_db()
        self.none_left.refresh_from_db()
        return self.orient.stock, self.none_left.stock

    def place_order(self):
        self.fill_cart()
        return services.place_order(self.user, **SHIPPING)


@override_settings(CURRENCY_SYMBOL='€')
class CheckoutViewTests(OrdersTestCase):
    def test_empty_cart_redirects_back(self):
        response = self.client.get(reverse('orders:checkout'))

        self.assertRedirects(response, reverse('orders:cart'))

    def test_checkout_page_prefills_customer_details(self):
        self.fill_cart()

        response = self.client.get(reverse('orders:checkout'))

        self.assertContains(response, 'Murder on the Orient Express')
        self.assertContains(response, '€25.48')  # 2 × 8.99 + 7.50
        self.assertEqual(response.context['form'].initial, {'full_name': 'Aoife Byrne', 'email': 'buyer@example.com'})

    def test_placing_an_order(self):
        self.fill_cart()

        response = self.client.post(reverse('orders:checkout'), SHIPPING, follow=True)

        order = Order.objects.get()
        self.assertRedirects(response, order.get_absolute_url())
        self.assertContains(response, f'Order {order.number} has been placed.')
        self.assertEqual(order.total, Decimal('25.48'))
        self.assertEqual(order.shipping_address, SHIPPING['shipping_address'])
        self.assertEqual(
            list(order.items.values_list('title', 'unit_price', 'quantity')),
            [('Murder on the Orient Express', Decimal('8.99'), 2), ('And Then There Were None', Decimal('7.50'), 1)],
        )
        self.assertEqual(self.refresh_stock(), (0, 4))
        self.assertEqual(cart_services.get_cart_lines(self.cart.id), [])

    def test_missing_shipping_details_are_reported(self):
        self.fill_cart()

        response = self.client.post(reverse('orders:checkout'), {**SHIPPING, 'shipping_address': ''})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].has_error('shipping_address'))
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.refresh_stock(), (2, 5))

    def test_stock_is_rechecked_when_ordering(self):
        self.fill_cart()
        Book.objects.filter(pk=self.orient.pk).update(stock=1)  # someone else bought a copy meanwhile

        response = self.client.post(reverse('orders:checkout'), SHIPPING)

        self.assertRedirects(response, reverse('orders:cart'))
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.refresh_stock(), (1, 5))  # nothing partially decremented
        self.assertEqual(len(cart_services.get_cart_lines(self.cart.id)), 2)

    def test_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('orders:checkout'))

        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('orders:checkout')}")


class OrderHistoryTests(OrdersTestCase):
    def test_order_list_shows_only_my_orders(self):
        mine = self.place_order()
        other = get_user_model().objects.create_user('other')
        cart_services.add_book(cart_services.get_cart(other), self.none_left)
        theirs = services.place_order(other, **SHIPPING)

        response = self.client.get(reverse('orders:list'))

        self.assertEqual(list(response.context['orders']), [mine])
        self.assertNotContains(response, theirs.number)

    def test_cannot_view_someone_elses_order(self):
        order = self.place_order()
        self.client.force_login(get_user_model().objects.create_user('other'))

        response = self.client.get(order.get_absolute_url())

        self.assertEqual(response.status_code, 404)

    def test_order_keeps_its_price_and_title_after_catalogue_changes(self):
        order = self.place_order()
        self.orient.price = Decimal('99.00')
        self.orient.save()
        self.none_left.delete()

        item_titles = list(order.items.values_list('title', 'unit_price', 'book'))

        self.assertEqual(item_titles, [
            ('Murder on the Orient Express', Decimal('8.99'), self.orient.pk),
            ('And Then There Were None', Decimal('7.50'), None),
        ])
        self.assertContains(self.client.get(order.get_absolute_url()), 'And Then There Were None')


class CancelOrderTests(OrdersTestCase):
    def test_customer_can_cancel_and_stock_is_restored(self):
        order = self.place_order()

        self.client.post(reverse('orders:cancel', args=[order.pk]))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.refresh_stock(), (2, 5))

    def test_shipped_orders_cannot_be_cancelled(self):
        order = self.place_order()
        Order.objects.filter(pk=order.pk).update(status=Order.Status.SHIPPED)

        response = self.client.post(reverse('orders:cancel', args=[order.pk]), follow=True)

        self.assertContains(response, 'has already been shipped')
        self.assertEqual(self.refresh_stock(), (0, 4))

    def test_cancel_requires_post(self):
        order = self.place_order()

        self.assertEqual(self.client.get(reverse('orders:cancel', args=[order.pk])).status_code, 405)


class OrderAdminTests(OrdersTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.place_order()
        self.client.force_login(self.staff)
        self.changelist = reverse('admin:orders_order_changelist')

    def run_action(self, action):
        return self.client.post(self.changelist, {'action': action, '_selected_action': [self.order.pk]})

    def test_changelist_and_search(self):
        response = self.client.get(self.changelist, {'q': 'buyer'})

        self.assertContains(response, self.order.number)

    def test_mark_shipped_action(self):
        self.run_action('mark_shipped')

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_cancel_and_restock_action(self):
        self.run_action('cancel_and_restock')

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.refresh_stock(), (2, 5))

    def test_orders_cannot_be_added_in_admin(self):
        self.assertEqual(self.client.get(reverse('admin:orders_order_add')).status_code, 403)

    def test_status_cannot_be_edited_directly(self):
        url = reverse('admin:orders_order_change', args=[self.order.pk])

        self.client.post(url, {
            'status': Order.Status.CANCELLED,
            'full_name': 'Changed', 'email': 'changed@example.com', 'shipping_address': 'Elsewhere',
            'items-TOTAL_FORMS': '2', 'items-INITIAL_FORMS': '2', 'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': self.order.items.all()[0].pk, 'items-0-order': self.order.pk,
            'items-1-id': self.order.items.all()[1].pk, 'items-1-order': self.order.pk,
        })

        self.order.refresh_from_db()
        self.assertEqual(self.order.full_name, 'Changed')
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(self.refresh_stock(), (0, 4))

    def test_order_items_are_read_only(self):
        response = self.client.get(reverse('admin:orders_order_change', args=[self.order.pk]))

        self.assertContains(response, 'Murder on the Orient Express')
        self.assertEqual(OrderItem.objects.count(), 2)
