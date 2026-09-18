import secrets
from decimal import Decimal

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Author, Book, Genre
from trading import services as trading
from trading.models import TradeRequest

AUTHORS = {
    'Frank Herbert': 'American science-fiction author best known for the Dune saga.',
    'Ursula K. Le Guin': 'American author of acclaimed science fiction and fantasy, including the Earthsea cycle.',
    'George Orwell': 'English novelist and essayist, author of Animal Farm and Nineteen Eighty-Four.',
    'Jane Austen': 'English novelist known for her witty social commentary on the British gentry.',
    'J.R.R. Tolkien': 'English writer and philologist, creator of Middle-earth.',
    'Agatha Christie': 'English crime novelist and creator of Hercule Poirot and Miss Marple.',
    'Arthur Conan Doyle': 'Scottish author and creator of the detective Sherlock Holmes.',
    'Sally Rooney': 'Irish novelist whose books explore modern relationships.',
    'Anna Burns': 'Northern Irish novelist and winner of the 2018 Booker Prize.',
    'Yuval Noah Harari': 'Israeli historian writing about the history and future of humankind.',
    'Daniel Kahneman': 'Nobel Prize-winning psychologist known for his work on judgement and decision-making.',
    'James Joyce': 'Irish modernist novelist and poet.',
}

# title, author, genre, ISBN-13, condition, price, copies, open to trade, seller
BOOKS = [
    ('Dune', 'Frank Herbert', 'Science Fiction', '9780441172719', 'new', '10.99', 12, False, 'admin'),
    ('The Left Hand of Darkness', 'Ursula K. Le Guin', 'Science Fiction', '9780441478125', 'like_new', '7.49', 1, True, 'reader'),
    ('Nineteen Eighty-Four', 'George Orwell', 'Classics', '9780141036144', 'good', '4.99', 2, True, 'bookworm'),
    ('Pride and Prejudice', 'Jane Austen', 'Classics', '9780141439518', 'new', '6.99', 15, False, 'admin'),
    ('Ulysses', 'James Joyce', 'Classics', '9780141182803', 'fair', '3.50', 0, True, 'bookworm'),
    ('The Hobbit', 'J.R.R. Tolkien', 'Fantasy', '9780261102217', 'good', '6.99', 1, True, 'reader'),
    ('The Silmarillion', 'J.R.R. Tolkien', 'Fantasy', '9780261102736', 'like_new', '8.99', 1, True, 'bookworm'),
    ('A Wizard of Earthsea', 'Ursula K. Le Guin', 'Fantasy', '9780141354309', 'fair', '2.99', 1, True, 'reader'),
    ('Murder on the Orient Express', 'Agatha Christie', 'Mystery', '9780007119318', 'new', '8.99', 10, False, 'admin'),
    ('The Hound of the Baskervilles', 'Arthur Conan Doyle', 'Mystery', '9780140437867', 'good', '3.99', 1, True, 'bookworm'),
    ('Normal People', 'Sally Rooney', 'Contemporary Fiction', '9780571334650', 'like_new', '6.49', 1, True, 'reader'),
    ('Milkman', 'Anna Burns', 'Contemporary Fiction', '9780571338757', 'new', '10.99', 5, False, 'admin'),
    ('Sapiens', 'Yuval Noah Harari', 'Non-fiction', '9780099590088', 'good', '7.99', 2, True, 'bookworm'),
    ('Thinking, Fast and Slow', 'Daniel Kahneman', 'Non-fiction', '9780141033570', 'fair', '4.49', 1, False, 'reader'),
]

# requester, their offered book (ISBN), owner, the owner's wanted book (ISBN), final status, message
TRADES = [
    ('reader', '9780141354309', 'bookworm', '9780261102736', 'pending', 'Happy to swap - mine has a few pencil notes.'),
    ('bookworm', '9780099590088', 'reader', '9780571334650', 'pending', ''),
    ('reader', '9780261102217', 'bookworm', '9780141036144', 'declined', 'Would you swap for a Tolkien?'),
]

DEMO_USERS = [
    # username, staff/superuser?, description
    ('admin', True, 'superuser: admin panel + shop listings'),
    ('reader', False, 'member: buys, sells and swaps books'),
    ('bookworm', False, 'member: second trader, to swap with reader'),
]


class Command(BaseCommand):
    """Project-wide demo data, so it is the one core module that knows about the other apps."""

    help = (
        'Create a demo superuser and member accounts, a sample catalogue (genres, authors, member listings) and '
        'sample swap offers. Listings are matched by ISBN and seller and offers by their books, so re-running '
        'refreshes them without duplicates. Demo passwords are generated on every run (or taken from '
        'DEMO_PASSWORD in the environment or .env) and printed to the console.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete every book, author and genre first (their swap offers and cart lines go too; '
                 'orders keep their snapshots).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            # Books first: authors and genres are protected while books reference them.
            Book.objects.all().delete()
            Author.objects.all().delete()
            Genre.objects.all().delete()
            self.stdout.write('Removed existing catalogue.')

        users, credentials = self.create_demo_users()
        self.seed_catalogue(users)
        self.seed_trades(users)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Demo accounts'))
        for username, password, description in credentials:
            self.stdout.write(f'  {username:<10} {password:<20} ({description})')
        self.stdout.write('These passwords are not stored anywhere else; re-run this command to rotate them.')

    def seed_catalogue(self, users):
        authors = {}
        for name, bio in AUTHORS.items():
            authors[name], _ = Author.objects.update_or_create(name=name, defaults={'bio': bio})

        created = 0
        for title, author, genre_name, isbn, condition, price, stock, open_to_trade, seller in BOOKS:
            genre, _ = Genre.objects.get_or_create(name=genre_name)
            values = {
                'title': title, 'author': authors[author], 'genre': genre, 'condition': condition,
                'price': Decimal(price), 'stock': stock, 'open_to_trade': open_to_trade,
            }
            Book(isbn=isbn, posted_by=users[seller], **values).full_clean()
            _, was_created = Book.objects.update_or_create(isbn=isbn, posted_by=users[seller], defaults=values)
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f'Catalogue ready: {len(BOOKS)} demo listings ({created} new) across '
            f'{Genre.objects.count()} genres and {Author.objects.count()} authors.'
        ))

    def seed_trades(self, users):
        created = 0
        for requester, offered_isbn, owner, wanted_isbn, status, message in TRADES:
            offered = Book.objects.get(isbn=offered_isbn, posted_by=users[requester])
            wanted = Book.objects.get(isbn=wanted_isbn, posted_by=users[owner])
            if TradeRequest.objects.filter(book_wanted=wanted, offered_book=offered).exists():
                continue
            # Go through the trading rules, as members do on the site.
            trade = trading.propose_trade(users[requester], wanted, offered, message)
            if status == TradeRequest.Status.DECLINED:
                trading.decline_trade(trade, users[owner])
            created += 1
        self.stdout.write(self.style.SUCCESS(f'Swap offers ready: {len(TRADES)} demo offers ({created} new).'))

    def create_demo_users(self):
        User = get_user_model()
        shared_password = config('DEMO_PASSWORD', default='')
        users, credentials = {}, []
        for username, is_admin, description in DEMO_USERS:
            password = shared_password or secrets.token_urlsafe(12)
            user, _ = User.objects.get_or_create(
                username=username, defaults={'email': f'{username}@booktrading.example.com'}
            )
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.set_password(password)
            user.save()
            users[username] = user
            credentials.append((username, password, description))
        return users, credentials
