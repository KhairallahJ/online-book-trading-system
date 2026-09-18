from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from catalog.models import Author, Book, Genre

from . import services
from .models import TradeRequest


class TradingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user('owner')
        cls.trader = User.objects.create_user('trader')
        cls.outsider = User.objects.create_user('outsider')
        genre = Genre.objects.create(name='Fantasy')
        author = Author.objects.create(name='Ursula K. Le Guin')

        def listing(title, isbn, posted_by, **extra):
            return Book.objects.create(
                title=title, author=author, genre=genre, isbn=isbn, price=Decimal('5.00'), posted_by=posted_by,
                **{'stock': 1, 'open_to_trade': True, **extra},
            )

        cls.earthsea = listing('A Wizard of Earthsea', '9780141354309', cls.owner)
        cls.lathe = listing('The Lathe of Heaven', '9780060512750', cls.owner, open_to_trade=False)
        cls.dispossessed = listing('The Dispossessed', '9780060512751', cls.trader)
        cls.tehanu = listing('Tehanu', '9780060512752', cls.trader, stock=2)
        cls.sold_out = listing('Tales from Earthsea', '9780060512753', cls.owner, stock=0)

    def offer(self, book_wanted=None, offered_book=None, requester=None):
        return services.propose_trade(
            requester or self.trader, book_wanted or self.earthsea, offered_book or self.dispossessed
        )

    def stock(self, *books):
        return tuple(Book.objects.get(pk=book.pk).stock for book in books)


class TradeRequestModelTests(TradingTestCase):
    def test_one_pending_offer_per_book_pair(self):
        self.offer()

        with self.assertRaises(IntegrityError), transaction.atomic():
            TradeRequest.objects.create(
                requester=self.trader, book_wanted=self.earthsea, offered_book=self.dispossessed
            )

    def test_answered_offers_do_not_block_a_new_one(self):
        TradeRequest.objects.create(
            requester=self.trader, book_wanted=self.earthsea, offered_book=self.dispossessed,
            status=TradeRequest.Status.DECLINED,
        )

        self.assertTrue(self.offer().is_pending)

    def test_a_book_cannot_be_swapped_for_itself(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TradeRequest.objects.create(
                requester=self.trader, book_wanted=self.earthsea, offered_book=self.earthsea
            )


class ProposeTradeServiceTests(TradingTestCase):
    def assert_rejected(self, message, **kwargs):
        with self.assertRaisesMessage(services.TradeError, message):
            self.offer(**kwargs)
        self.assertFalse(TradeRequest.objects.exists())

    def test_valid_offer_is_pending(self):
        trade = self.offer()

        self.assertEqual(trade.status, TradeRequest.Status.PENDING)
        self.assertEqual(self.stock(self.earthsea, self.dispossessed), (1, 1))  # nothing changes hands yet

    def test_cannot_offer_on_own_listing(self):
        self.assert_rejected("can't make an offer on your own listing", requester=self.owner,
                             offered_book=self.lathe)

    def test_listing_must_be_open_to_trade(self):
        self.assert_rejected('is not open to swaps', book_wanted=self.lathe)

    def test_listing_must_be_in_stock(self):
        self.assert_rejected('is no longer available', book_wanted=self.sold_out)

    def test_offered_book_must_belong_to_requester(self):
        self.assert_rejected('only offer books from your own listings', requester=self.outsider)

    def test_duplicate_pending_offer_is_rejected(self):
        self.offer()

        with self.assertRaisesMessage(services.TradeError, 'already offered'):
            self.offer()

    def test_tradeable_books_excludes_own_closed_and_sold_out_listings(self):
        self.assertEqual(
            set(services.tradeable_books(self.trader)), {self.earthsea}
        )
        self.assertEqual(
            set(services.tradeable_books(self.owner)), {self.dispossessed, self.tehanu}
        )


class RespondToTradeServiceTests(TradingTestCase):
    def test_accepting_swaps_one_copy_of_each_book(self):
        trade = self.offer(offered_book=self.tehanu)

        services.accept_trade(trade, self.owner)

        trade.refresh_from_db()
        self.assertEqual(trade.status, TradeRequest.Status.ACCEPTED)
        self.assertIsNotNone(trade.responded_at)
        self.assertEqual(self.stock(self.earthsea, self.tehanu), (0, 1))

    def test_accepting_declines_offers_that_can_no_longer_happen(self):
        rival = get_user_model().objects.create_user('rival')
        rival_book = Book.objects.create(
            title='Rocannon', author=self.earthsea.author, genre=self.earthsea.genre, isbn='9780060512754',
            price=1, posted_by=rival,
        )
        rival_offer = self.offer(offered_book=rival_book, requester=rival)
        other_offer_with_spare_copy = services.propose_trade(self.trader, self.earthsea, self.tehanu)
        trade = self.offer()

        services.accept_trade(trade, self.owner)

        # The Earthsea copy is gone, so every other offer for it is declined.
        rival_offer.refresh_from_db()
        other_offer_with_spare_copy.refresh_from_db()
        self.assertEqual(rival_offer.status, TradeRequest.Status.DECLINED)
        self.assertEqual(other_offer_with_spare_copy.status, TradeRequest.Status.DECLINED)

    def test_only_the_owner_can_accept(self):
        trade = self.offer()

        with self.assertRaisesMessage(services.TradeError, 'Only the owner'):
            services.accept_trade(trade, self.trader)
        self.assertEqual(self.stock(self.earthsea, self.dispossessed), (1, 1))

    def test_accepting_fails_if_a_book_sold_meanwhile(self):
        trade = self.offer()
        Book.objects.filter(pk=self.dispossessed.pk).update(stock=0)

        with self.assertRaisesMessage(services.TradeError, 'no longer in stock'):
            services.accept_trade(trade, self.owner)

        trade.refresh_from_db()
        self.assertTrue(trade.is_pending)
        self.assertEqual(self.stock(self.earthsea), (1,))

    def test_answered_offers_cannot_be_answered_again(self):
        trade = self.offer()
        services.decline_trade(trade, self.owner)

        with self.assertRaisesMessage(services.TradeError, 'already been declined'):
            services.accept_trade(trade, self.owner)

    def test_withdraw_removes_the_offer(self):
        trade = self.offer()

        services.withdraw_trade(trade, self.trader)

        self.assertFalse(TradeRequest.objects.exists())

    def test_deleting_a_listing_removes_its_offers(self):
        self.offer()

        self.dispossessed.delete()

        self.assertFalse(TradeRequest.objects.exists())


class TradingPageTests(TradingTestCase):
    def test_browse_lists_tradeable_books_for_everyone(self):
        response = self.client.get(reverse('trading:browse'))

        self.assertEqual(
            {book.title for book in response.context['books']},
            {'A Wizard of Earthsea', 'The Dispossessed', 'Tehanu'},
        )
        self.assertContains(response, reverse('trading:propose', args=[self.earthsea.id]))

    def test_browse_hides_own_books_and_searches(self):
        self.client.force_login(self.trader)

        everything = self.client.get(reverse('trading:browse'))
        searched = self.client.get(reverse('trading:browse'), {'q': 'tehanu'})

        self.assertEqual([book.title for book in everything.context['books']], ['A Wizard of Earthsea'])
        self.assertEqual(list(searched.context['books']), [])

    def test_browse_filters_by_condition(self):
        Book.objects.filter(pk=self.tehanu.pk).update(condition=Book.Condition.FAIR)

        response = self.client.get(reverse('trading:browse'), {'condition': 'fair'})

        self.assertEqual([book.title for book in response.context['books']], ['Tehanu'])

    def test_propose_requires_login(self):
        url = reverse('trading:propose', args=[self.earthsea.id])

        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_propose_form_offers_only_my_in_stock_books(self):
        self.client.force_login(self.trader)

        response = self.client.get(reverse('trading:propose', args=[self.earthsea.id]))

        self.assertEqual(
            set(response.context['form'].fields['offered_book'].queryset), {self.dispossessed, self.tehanu}
        )

    def test_sending_an_offer(self):
        self.client.force_login(self.trader)

        response = self.client.post(
            reverse('trading:propose', args=[self.earthsea.id]),
            {'offered_book': self.dispossessed.id, 'message': 'Mine is signed!'},
            follow=True,
        )

        trade = TradeRequest.objects.get()
        self.assertEqual((trade.requester, trade.book_wanted, trade.offered_book), (self.trader, self.earthsea, self.dispossessed))
        self.assertEqual(trade.message, 'Mine is signed!')
        self.assertRedirects(response, f"{reverse('trading:my_trades')}?box=sent")
        self.assertContains(response, 'Your swap offer for &quot;A Wizard of Earthsea&quot; was sent to owner.')

    def test_offering_someone_elses_book_is_rejected(self):
        self.client.force_login(self.trader)

        response = self.client.post(
            reverse('trading:propose', args=[self.earthsea.id]), {'offered_book': self.lathe.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].has_error('offered_book'))
        self.assertFalse(TradeRequest.objects.exists())

    def test_duplicate_offer_is_reported_on_the_form(self):
        self.offer()
        self.client.force_login(self.trader)

        response = self.client.post(
            reverse('trading:propose', args=[self.earthsea.id]), {'offered_book': self.dispossessed.id}
        )

        self.assertContains(response, 'You have already offered')
        self.assertEqual(TradeRequest.objects.count(), 1)

    def test_cannot_open_offer_page_for_own_or_closed_listing(self):
        self.client.force_login(self.owner)

        own = self.client.get(reverse('trading:propose', args=[self.earthsea.id]))
        self.client.force_login(self.trader)
        closed = self.client.get(reverse('trading:propose', args=[self.lathe.id]))

        self.assertRedirects(own, self.earthsea.get_absolute_url())
        self.assertRedirects(closed, self.lathe.get_absolute_url())

    def test_member_without_stock_is_told_to_list_a_book(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse('trading:propose', args=[self.earthsea.id]))

        self.assertContains(response, 'You need a book in stock to offer.')

    def test_my_trades_shows_received_and_sent_offers(self):
        trade = self.offer()

        self.client.force_login(self.owner)
        received = self.client.get(reverse('trading:my_trades'))
        self.client.force_login(self.trader)
        sent = self.client.get(reverse('trading:my_trades'), {'box': 'sent'})
        nothing_received = self.client.get(reverse('trading:my_trades'))

        self.assertEqual(list(received.context['trades']), [trade])
        self.assertEqual(received.context['pending_offer_count'], 1)
        self.assertContains(received, reverse('trading:accept', args=[trade.pk]))
        self.assertEqual(list(sent.context['trades']), [trade])
        self.assertContains(sent, reverse('trading:withdraw', args=[trade.pk]))
        self.assertEqual(list(nothing_received.context['trades']), [])

    def test_owner_accepts_from_my_trades(self):
        trade = self.offer()
        self.client.force_login(self.owner)

        response = self.client.post(reverse('trading:accept', args=[trade.pk]), follow=True)

        self.assertContains(response, 'Swap agreed')
        trade.refresh_from_db()
        self.assertEqual(trade.status, TradeRequest.Status.ACCEPTED)

    def test_owner_declines_from_my_trades(self):
        trade = self.offer()
        self.client.force_login(self.owner)

        self.client.post(reverse('trading:decline', args=[trade.pk]))

        trade.refresh_from_db()
        self.assertEqual(trade.status, TradeRequest.Status.DECLINED)

    def test_only_the_owner_can_respond(self):
        trade = self.offer()

        for user in (self.trader, self.outsider):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.post(reverse('trading:accept', args=[trade.pk])).status_code, 404)
                self.assertEqual(self.client.post(reverse('trading:decline', args=[trade.pk])).status_code, 404)
        trade.refresh_from_db()
        self.assertTrue(trade.is_pending)

    def test_only_the_requester_can_withdraw(self):
        trade = self.offer()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('trading:withdraw', args=[trade.pk])).status_code, 404)

        self.client.force_login(self.trader)
        self.client.post(reverse('trading:withdraw', args=[trade.pk]))

        self.assertFalse(TradeRequest.objects.exists())

    def test_responses_require_post(self):
        trade = self.offer()
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(reverse('trading:accept', args=[trade.pk])).status_code, 405)

    def test_book_detail_links_to_the_offer_page(self):
        self.client.force_login(self.trader)

        response = self.client.get(self.earthsea.get_absolute_url())

        self.assertContains(response, reverse('trading:propose', args=[self.earthsea.id]))


class TradeAdminTests(TradingTestCase):
    def setUp(self):
        self.trade = self.offer()
        admin_user = get_user_model().objects.create_superuser('boss', 'boss@example.com', 'unused')
        self.client.force_login(admin_user)

    def test_changelist_search(self):
        response = self.client.get(reverse('admin:trading_traderequest_changelist'), {'q': 'earthsea'})

        self.assertContains(response, 'owner')
        self.assertEqual(response.context['cl'].result_count, 1)

    def test_decline_action(self):
        self.client.post(reverse('admin:trading_traderequest_changelist'), {
            'action': 'decline_selected', '_selected_action': [self.trade.pk],
        })

        self.trade.refresh_from_db()
        self.assertEqual(self.trade.status, TradeRequest.Status.DECLINED)

    def test_offers_cannot_be_added_in_admin(self):
        self.assertEqual(self.client.get(reverse('admin:trading_traderequest_add')).status_code, 403)
