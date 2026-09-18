from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.test import TestCase
from django.urls import reverse

from .models import Author, Book, Genre
from .search import build_search_query, search_books


class CatalogTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user('seller')
        cls.fantasy = Genre.objects.create(name='Fantasy')
        cls.tolkien = Author.objects.create(name='J.R.R. Tolkien', bio='English writer and philologist.')
        cls.hobbit = Book.objects.create(
            title='The Hobbit',
            author=cls.tolkien,
            genre=cls.fantasy,
            isbn='9780261102217',
            condition=Book.Condition.LIKE_NEW,
            price=Decimal('10.99'),
            stock=3,
            posted_by=cls.seller,
        )


class BookModelTests(CatalogTestCase):
    def test_str_includes_author(self):
        self.assertEqual(str(self.hobbit), 'The Hobbit by J.R.R. Tolkien')

    def test_isbn_must_be_10_or_13_digits(self):
        for isbn in ['12345', '978-0261102217', 'abcdefghij']:
            with self.subTest(isbn=isbn):
                self.hobbit.isbn = isbn
                with self.assertRaises(ValidationError):
                    self.hobbit.full_clean()

    def test_isbn10_with_check_letter_is_valid(self):
        self.hobbit.isbn = '026110221X'
        self.hobbit.full_clean()


class CatalogPageTests(CatalogTestCase):
    def test_book_list(self):
        response = self.client.get(reverse('catalog:book_list'))

        self.assertContains(response, 'The Hobbit')
        self.assertContains(response, 'J.R.R. Tolkien')

    def test_book_detail_links_to_author_and_genre(self):
        response = self.client.get(reverse('catalog:book_detail', args=[self.hobbit.id]))

        self.assertContains(response, '9780261102217')
        self.assertContains(response, 'Like new')
        self.assertContains(response, 'seller')
        self.assertContains(response, reverse('catalog:author_detail', args=[self.tolkien.id]))
        self.assertContains(response, reverse('catalog:genre_books', args=['Fantasy']))

    def test_genre_lookup_is_case_insensitive(self):
        response = self.client.get(reverse('catalog:genre_books', args=['fantasy']))

        self.assertContains(response, 'The Hobbit')

    def test_author_page_lists_their_books(self):
        response = self.client.get(reverse('catalog:author_detail', args=[self.tolkien.id]))

        self.assertContains(response, 'English writer and philologist.')
        self.assertContains(response, 'The Hobbit')

    def test_navigation_lists_genres(self):
        response = self.client.get(reverse('catalog:book_list'))

        self.assertContains(response, f'href="{reverse("catalog:genre_books", args=["Fantasy"])}"')


class ListingManagementTests(CatalogTestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user('staff', is_staff=True)
        self.member = User.objects.create_user('member')

    def book_data(self, **overrides):
        return {
            'title': 'The Silmarillion',
            'author_name': 'J.R.R. Tolkien',
            'genre': self.fantasy.id,
            'isbn': '9780261102736',
            'condition': Book.Condition.GOOD,
            'price': '12.50',
            'stock': 1,
            'open_to_trade': 'on',
            **overrides,
        }

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(reverse('catalog:create_book'))

        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('catalog:create_book')}")

    def test_members_can_list_a_book(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse('catalog:create_book'), self.book_data())

        book = Book.objects.get(title='The Silmarillion')
        self.assertRedirects(response, book.get_absolute_url())
        self.assertEqual(book.posted_by, self.member)
        self.assertEqual(book.author, self.tolkien)  # matched by name, not duplicated
        self.assertTrue(book.open_to_trade)

    def test_new_author_names_create_an_author(self):
        self.client.force_login(self.member)

        self.client.post(reverse('catalog:create_book'), self.book_data(author_name='  Christopher   Tolkien '))

        self.assertEqual(Book.objects.get(title='The Silmarillion').author.name, 'Christopher Tolkien')

    def test_posted_by_cannot_be_forged(self):
        self.client.force_login(self.member)

        self.client.post(reverse('catalog:create_book'), self.book_data(posted_by=self.staff.id))

        self.assertEqual(Book.objects.get(title='The Silmarillion').posted_by, self.member)

    def test_owner_can_edit_their_listing(self):
        self.client.force_login(self.seller)

        self.client.post(
            reverse('catalog:edit_book', args=[self.hobbit.id]),
            self.book_data(title='The Hobbit', isbn=self.hobbit.isbn, price='8.99'),
        )

        self.hobbit.refresh_from_db()
        self.assertEqual(self.hobbit.price, Decimal('8.99'))
        self.assertEqual(self.hobbit.posted_by, self.seller)

    def test_staff_can_edit_any_listing(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('catalog:edit_book', args=[self.hobbit.id]))

        self.assertContains(response, 'value="J.R.R. Tolkien"')

    def test_other_members_cannot_edit_or_delete(self):
        self.client.force_login(self.member)

        edit = self.client.post(reverse('catalog:edit_book', args=[self.hobbit.id]), self.book_data())
        delete = self.client.post(reverse('catalog:delete_book', args=[self.hobbit.id]))

        self.assertEqual((edit.status_code, delete.status_code), (403, 403))
        self.assertTrue(Book.objects.filter(pk=self.hobbit.pk, title='The Hobbit').exists())

    def test_owner_can_delete_their_listing(self):
        self.client.force_login(self.seller)
        url = reverse('catalog:delete_book', args=[self.hobbit.id])
        self.assertContains(self.client.get(url), 'Delete this listing?')

        response = self.client.post(url)

        self.assertRedirects(response, reverse('catalog:my_listings'))
        self.assertFalse(Book.objects.filter(pk=self.hobbit.pk).exists())

    def test_same_isbn_can_be_listed_by_several_members(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse('catalog:create_book'), self.book_data(isbn=self.hobbit.isbn))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Book.objects.filter(isbn=self.hobbit.isbn).count(), 2)

    def test_invalid_isbn_is_rejected(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse('catalog:create_book'), self.book_data(isbn='12-34'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a 10- or 13-digit ISBN')

    def test_my_listings_shows_only_my_books(self):
        Book.objects.create(
            title='Mine', author=self.tolkien, genre=self.fantasy, isbn='9780000000002', price=1, posted_by=self.member
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse('catalog:my_listings'))

        self.assertEqual([b.title for b in response.context['books']], ['Mine'])

    def test_detail_shows_owner_controls_only_to_owner(self):
        url = reverse('catalog:book_detail', args=[self.hobbit.id])
        edit_url = reverse('catalog:edit_book', args=[self.hobbit.id])

        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(url), edit_url)
        self.client.force_login(self.seller)
        owner_view = self.client.get(url)
        self.assertContains(owner_view, edit_url)
        self.assertContains(owner_view, 'This is your listing.')


class SearchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = get_user_model().objects.create_user('seller')
        fantasy = Genre.objects.create(name='Fantasy')
        classics = Genre.objects.create(name='Classics')
        tolkien = Author.objects.create(name='J.R.R. Tolkien')
        austen = Author.objects.create(name='Jane Austen')
        cls.hobbit = Book.objects.create(
            title='The Hobbit', author=tolkien, genre=fantasy, isbn='9780261102217', condition='good',
            price=Decimal('10.99'), stock=3, posted_by=cls.seller,
        )
        cls.lotr = Book.objects.create(
            title='The Lord of the Rings', author=tolkien, genre=fantasy, isbn='9780261103252', condition='new',
            price=Decimal('25.00'), stock=0, posted_by=cls.seller,
        )
        cls.emma = Book.objects.create(
            title='Emma', author=austen, genre=classics, isbn='9780141439587', condition='fair',
            price=Decimal('6.99'), stock=5, posted_by=cls.seller,
        )
        cls.fantasy = fantasy

    def search(self, **params):
        return list(search_books(Book.objects.all(), **params))


class SearchBooksTests(SearchTestCase):
    def test_no_criteria_returns_everything_sorted_by_title(self):
        self.assertEqual(self.search(), [self.emma, self.hobbit, self.lotr])

    def test_title_search_is_case_insensitive(self):
        self.assertEqual(self.search(q='hOBBIT'), [self.hobbit])

    def test_search_matches_author_name(self):
        self.assertEqual(self.search(q='tolkien'), [self.hobbit, self.lotr])

    def test_search_matches_isbn_typed_with_hyphens(self):
        self.assertEqual(self.search(q='978-0-14-143958'), [self.emma])

    def test_price_range(self):
        self.assertEqual(self.search(min_price=Decimal('7'), max_price=Decimal('11')), [self.hobbit])

    def test_price_range_bounds_are_inclusive(self):
        self.assertEqual(self.search(min_price=Decimal('6.99'), max_price=Decimal('10.99')), [self.emma, self.hobbit])

    def test_condition_filter(self):
        self.assertEqual(self.search(condition=['new']), [self.lotr])
        self.assertEqual(self.search(condition=['new', 'fair']), [self.emma, self.lotr])

    def test_text_condition_and_price_combine(self):
        self.assertEqual(self.search(q='tolkien', condition=['good', 'new'], max_price=Decimal('20')), [self.hobbit])

    def test_criteria_are_combined_into_one_q_object(self):
        query = build_search_query(q='tolkien', condition=['good'], min_price=Decimal('1'), max_price=Decimal('20'))

        self.assertEqual(query.connector, 'AND')
        self.assertEqual(len(query.children), 4)  # text match (an OR of title/author/ISBN), condition, min, max
        self.assertEqual(list(Book.objects.filter(query)), [self.hobbit])

    def test_empty_criteria_match_everything(self):
        self.assertEqual(build_search_query(q='   ', condition=[]), Q())

    def test_genre_and_stock_filters(self):
        self.assertEqual(self.search(genre=self.fantasy, in_stock=True), [self.hobbit])

    def test_sort_by_price_descending(self):
        self.assertEqual(self.search(sort='-price'), [self.lotr, self.hobbit, self.emma])

    def test_sort_by_newest_listing(self):
        self.assertEqual(self.search(sort='newest'), [self.emma, self.lotr, self.hobbit])

    def test_unknown_sort_falls_back_to_title(self):
        self.assertEqual(self.search(sort='stock; DROP TABLE'), [self.emma, self.hobbit, self.lotr])


class BookListPageTests(SearchTestCase):
    def get(self, **params):
        return self.client.get(reverse('catalog:book_list'), params)

    def test_query_string_filters_the_list(self):
        response = self.get(q='tolkien', max_price='20')

        self.assertEqual(list(response.context['books']), [self.hobbit])
        self.assertContains(response, 'value="tolkien"')

    def test_condition_checkboxes_filter_the_list(self):
        response = self.client.get(reverse('catalog:book_list') + '?condition=new&condition=good')

        self.assertEqual(list(response.context['books']), [self.hobbit, self.lotr])
        self.assertContains(response, 'value="new" class="form-check-input" id="id_condition_0" checked')

    def test_unknown_condition_is_ignored_and_reported(self):
        response = self.get(condition='mint')

        self.assertEqual(len(response.context['books']), 3)
        self.assertContains(response, 'Select a valid choice.')

    def test_invalid_price_is_ignored_and_reported(self):
        response = self.get(q='tolkien', min_price='cheap')

        self.assertEqual(list(response.context['books']), [self.hobbit, self.lotr])
        self.assertContains(response, 'Enter a number.')

    def test_min_price_above_max_price_is_reported(self):
        response = self.get(min_price='20', max_price='5')

        self.assertContains(response, 'Max price must be at least the min price.')
        self.assertEqual(list(response.context['books']), [self.lotr])

    def test_results_are_paginated(self):
        genre = Genre.objects.create(name='Poetry')
        author = Author.objects.create(name='Seamus Heaney')
        for i in range(13):
            Book.objects.create(
                title=f'Poems {i:02}', author=author, genre=genre, isbn=f'97800000000{i:02}', price=5, stock=1,
                posted_by=self.seller,
            )

        first = self.get(q='poems')
        second = self.get(q='poems', page=2)

        self.assertEqual(first.context['paginator'].count, 13)
        self.assertEqual(len(first.context['books']), 12)
        self.assertEqual([b.title for b in second.context['books']], ['Poems 12'])
        # The "Next" link keeps the active filters.
        self.assertContains(first, 'href="?q=poems&amp;page=2"')

    def test_list_uses_a_fixed_number_of_queries(self):
        # count + one page of books (author/genre/seller joined) + genres for the nav menu and for the filter form
        with self.assertNumQueries(4):
            self.get()

    def test_genre_page_prefilters_and_keeps_other_filters(self):
        response = self.client.get(reverse('catalog:genre_books', args=['fantasy']), {'in_stock': 'on'})

        self.assertEqual(list(response.context['books']), [self.hobbit])
        self.assertEqual(response.context['genre'], self.fantasy)


class BookSearchApiTests(SearchTestCase):
    def test_returns_filtered_json(self):
        response = self.client.get(reverse('catalog:book_search_api'), {'q': 'austen'})

        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['title'], 'Emma')
        self.assertEqual(data['results'][0]['price'], '6.99')
        self.assertEqual(data['results'][0]['condition'], 'fair')
        self.assertEqual(data['results'][0]['posted_by'], 'seller')
        self.assertTrue(data['results'][0]['url'].endswith(self.emma.get_absolute_url()))

    def test_condition_and_price_range_parameters(self):
        response = self.client.get(
            reverse('catalog:book_search_api') + '?condition=good&condition=new&min_price=10&max_price=30'
        )

        self.assertEqual([book['title'] for book in response.json()['results']], ['The Hobbit', 'The Lord of the Rings'])

    def test_invalid_parameters_return_400(self):
        response = self.client.get(reverse('catalog:book_search_api'), {'max_price': '-1'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('max_price', response.json()['errors'])
