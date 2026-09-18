import os
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.views import View

from catalog.models import Author, Book, Genre
from trading.models import TradeRequest

from .mixins import StaffRequiredMixin
from .templatetags.core_extras import cover_hue, cover_title_class, currency


class CurrencyFilterTests(SimpleTestCase):
    @override_settings(CURRENCY_SYMBOL='€')
    def test_formats_with_two_decimals_and_thousands_separator(self):
        self.assertEqual(currency(Decimal('1234.5')), '€1,234.50')
        self.assertEqual(currency(9), '€9.00')

    def test_empty_values_render_blank(self):
        self.assertEqual(currency(None), '')
        self.assertEqual(currency(''), '')


class BookCoverFilterTests(SimpleTestCase):
    def test_cover_hue_is_stable_and_in_range(self):
        self.assertEqual(cover_hue('Dune'), cover_hue('Dune'))
        self.assertTrue(all(0 <= cover_hue(title) < 360 for title in ['Dune', 'Emma', '', 'Ulysses']))

    def test_long_words_get_smaller_cover_titles(self):
        self.assertEqual(cover_title_class('The Hobbit'), '')
        self.assertEqual(cover_title_class('Nineteen Eighty-Four'), 'book-cover-long-words')
        self.assertEqual(cover_title_class('The Hound of the Baskervilles'), 'book-cover-very-long-words')


class StaffOnlyView(StaffRequiredMixin, View):
    def get(self, request):
        return HttpResponse('ok')


class StaffRequiredMixinTests(TestCase):
    def get(self, user):
        request = RequestFactory().get('/staff-only/')
        request.user = user
        return StaffOnlyView.as_view()(request)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.get(AnonymousUser())

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_non_staff_user_is_forbidden(self):
        with self.assertRaises(PermissionDenied):
            self.get(get_user_model().objects.create_user('customer'))

    def test_staff_user_is_allowed(self):
        response = self.get(get_user_model().objects.create_user('staff', is_staff=True))

        self.assertEqual(response.status_code, 200)


class SiteTests(TestCase):
    def test_health_check(self):
        response = self.client.get(reverse('core:health'))

        self.assertEqual(response.json(), {'status': 'ok'})

    def test_custom_404_page(self):
        response = self.client.get('/no-such-page/')

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')

    def test_flash_messages_are_rendered(self):
        member = get_user_model().objects.create_user('member')
        self.client.force_login(member)

        response = self.client.post(reverse('catalog:create_book'), {
            'title': 'Emma',
            'author_name': 'Jane Austen',
            'genre': Genre.objects.create(name='Classics').id,
            'isbn': '9780141439587',
            'condition': 'good',
            'price': '6.99',
            'stock': 2,
        }, follow=True)

        self.assertContains(response, '&quot;Emma&quot; is now listed.')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SeedDemoDataTests(TestCase):
    def seed(self, *args):
        out = StringIO()
        call_command('seed_demo_data', *args, stdout=out)
        return out.getvalue()

    @staticmethod
    def printed_password(output, username):
        line = next(line for line in output.splitlines() if line.strip().startswith(f'{username} '))
        return line.split()[1]

    def test_seeds_catalogue_and_prints_working_credentials(self):
        output = self.seed()

        self.assertEqual(Book.objects.count(), 14)
        self.assertEqual(Genre.objects.count(), 6)
        self.assertTrue(Book.objects.filter(stock=0).exists())  # something to exercise the in-stock filter
        self.assertEqual(set(Book.objects.values_list('condition', flat=True)), {'new', 'like_new', 'good', 'fair'})
        admin = authenticate(username='admin', password=self.printed_password(output, 'admin'))
        reader = authenticate(username='reader', password=self.printed_password(output, 'reader'))
        bookworm = authenticate(username='bookworm', password=self.printed_password(output, 'bookworm'))
        self.assertTrue(admin.is_superuser)
        self.assertFalse(reader.is_staff)
        # Both members have books open to trade, so they can swap with each other.
        for member in (reader, bookworm):
            self.assertTrue(member.listings.filter(open_to_trade=True, stock__gt=0).exists())
        self.assertEqual(TradeRequest.objects.filter(status='pending').count(), 2)
        self.assertEqual(TradeRequest.objects.filter(status='declined').count(), 1)
        self.assertEqual(TradeRequest.objects.filter(book_wanted__posted_by=reader, status='pending').count(), 1)

    def test_rerun_refreshes_demo_books_without_duplicates(self):
        self.seed()
        Book.objects.filter(isbn='9780441172719').update(stock=0, price=Decimal('1.00'))

        output = self.seed()

        self.assertIn('14 demo listings (0 new)', output)
        self.assertIn('3 demo offers (0 new)', output)
        self.assertEqual(Book.objects.count(), 14)
        self.assertEqual(TradeRequest.objects.count(), 3)
        dune = Book.objects.get(isbn='9780441172719')
        self.assertEqual((dune.stock, dune.price), (12, Decimal('10.99')))

    def test_reset_removes_other_books(self):
        self.seed()
        Book.objects.create(
            title='Staff pick', author=Author.objects.first(), genre=Genre.objects.first(),
            isbn='9780000000001', price=Decimal('1.00'), stock=1, posted_by=get_user_model().objects.first(),
        )

        self.seed('--reset')

        self.assertFalse(Book.objects.filter(title='Staff pick').exists())
        self.assertEqual(Book.objects.count(), 14)
        self.assertEqual(TradeRequest.objects.count(), 3)

    @mock.patch.dict(os.environ, {'DEMO_PASSWORD': 'known-demo-password'})
    def test_password_can_come_from_the_environment(self):
        self.seed()

        self.assertIsNotNone(authenticate(username='reader', password='known-demo-password'))
