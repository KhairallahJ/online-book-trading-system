# Online Book Trading System

**Online Book Trading System | Django** — a web-based marketplace featuring listings, search, and admin
controls, designed with a modular, maintainable architecture.

Members list the books they own, including each copy's condition. Other members can buy those copies or
offer one of their own books in exchange. Staff moderate everything from the Django admin.

**Stack:** Python 3.10+ · Django 5.2 LTS · Bootstrap 5 with a custom theme · SQLite (PostgreSQL via `DATABASE_URL`) ·
python-decouple · dj-database-url

## Features

- **Listings**: any signed-in member can list a book with its title, ISBN, author, genre, condition
  (*new*, *like new*, *good* or *fair*), price and number of copies. Only the member who posted a listing,
  or staff, can edit or delete it. *My listings* shows everything you have for sale.
- **Book swaps** (the `trading` app):
  - Browse the books other members are open to swapping, then offer one of your own in-stock books in
    exchange.
  - The owner accepts or declines the offer under *My trades*, and the requester can withdraw an offer until
    it's answered.
  - Accepting takes one copy of each book out of stock inside a locked transaction. Any other pending offer
    that relied on a copy that has run out is declined automatically.
- **Search**:
  - Case-insensitive text search across title, author and ISBN (hyphens ignored).
  - Filters for condition (multi-select), a min/max price range, genre and in-stock only, all combined into
    one `Q` object.
  - Sorting, including newest listings first. Filters survive pagination, and the same search is available
    as JSON at `/books/api/`.
- **Buying**: a per-member cart with stock checks (you can't buy your own listing), and a transactional
  checkout with row locking, stock decrements and price snapshots. Also order history and cancellation,
  which restocks the books.
- **Accounts**: sign-up with Django's password validators and unique emails, log in/out, a profile page and
  password change.
- **Admin controls**:
  - **Listings**: condition, trading, genre and date filters; inline price/stock/trading edits; seller
    search. Bulk actions mark books "out of stock" or "withdraw from trading".
  - **Swap offers**: read-only apart from the message, with a bulk "decline" action that goes through the
    trading rules.
  - **Orders**: "mark shipped" and "cancel and restock" actions.
  - **Authors and genres**: book counts shown for each; carts can be inspected too.
- **Look and feel:** a warm "bookshop" theme with paper-toned pages, forest-green actions, terracotta accents
  and serif headings (Fraunces with Source Sans 3). Each listing gets a generated cover tinted from its title,
  the home page has a hero section, and the layout works down to phone widths.

## Architecture

The project is a set of focused Django apps. Each app owns its models, views, templates and tests, and has
its own `urls.py` with an `app_name`. The project URLconf includes each one under a namespace, so every
link is namespaced, for example `catalog:book_detail`, `trading:propose` or `orders:checkout`.

```
.
├── booktradingsystem/   Project package: settings (python-decouple), root URLconf, WSGI/ASGI
├── core/                Shared layer: base template and theme (static/core/css/theme.css), error pages,
│                        form/permission mixins, currency and cover template filters, /health/ check,
│                        project-wide seed_demo_data command
├── accounts/            Sign up, log in/out, profile, password change
├── catalog/             Author, Genre and Book (listing) models; browse, search and filter views;
│                        search.py (Q-object search); JSON search API; listing management
├── trading/             TradeRequest model; services.py (swap rules); browse/offer/respond views
├── orders/              Cart, CartItem, Order and OrderItem models; cart.py and services.py
│                        (cart and checkout rules); cart, checkout and order history views
├── manage.py
├── requirements.txt
└── .env.example
```

| URL prefix | App | Main pages |
| --- | --- | --- |
| `/` | catalog | Listing search, `/books/<id>/`, `/books/add/`, `/books/mine/`, `/genre/<name>/`, `/authors/<id>/`, `/books/api/` |
| `/trading/` | trading | Tradeable books, `books/<id>/offer/`, `mine/` (received/sent), `<id>/accept/` · `decline/` · `withdraw/` |
| `/orders/` | orders | `cart/`, `checkout/`, order history, `<id>/`, `<id>/cancel/` |
| `/accounts/` | accounts | `signup/`, `login/`, `logout/`, `profile/`, `password/` |
| `/admin/` | Django admin | Admin controls |
| `/health/` | core | JSON health check (also pings the database) |

### Data model

```
User 1 ── * Book (posted_by) * ── 1 Author
                             * ── 1 Genre
TradeRequest: requester ── User, book_wanted ── Book, offered_book ── Book
              status: pending → accepted | declined
User 1 ── 1 Cart 1 ── * CartItem * ── 1 Book
User 1 ── * Order 1 ── * OrderItem (title and price snapshot; book set to NULL if the listing is deleted)
```

Constraints enforced in the database:

- At most one *pending* offer per pair of books, and a book can't be swapped for itself.
- One cart line per book, and author/genre deletes are blocked while books use them (`PROTECT`).
- Indexes back the frequent lookups: ISBN, offers by requester/status and by listing/status, and each
  user's recent orders.

### How the apps stay decoupled

```
accounts ─────────────┐
catalog  ─────────────┤
trading  ── catalog ──┼──► core
orders   ─────────────┘
```

- **Dependencies point one way.** `trading` and `orders` refer to books through string foreign keys
  (`'catalog.Book'`) with no reverse accessor, so `catalog` knows nothing about swaps, carts or orders.
  When they need the Book model, they resolve it through that foreign key (`services.book_model()`)
  instead of importing `catalog.models`. `trading` reuses the catalog's public search helper,
  `catalog.search`.
- **Business rules live in service modules.** Views and admin actions call `trading/services.py`,
  `orders/cart.py` and `orders/services.py` instead of changing rows directly. Those modules hold the
  ownership checks, stock locking and automatic declines, so the rules live in one place and are unit
  tested.
- **Snapshots at the boundary.** Order items store the title and unit price at purchase time, so catalogue
  edits (or deleted listings) never change past orders.
- **Shared code lives in `core`.** Its mixins, forms and template tags import no other project app. The
  exceptions are the site-wide base template, which links to every app, and the project-wide
  `seed_demo_data` command.

## Getting started

### Prerequisites

- Python 3.10–3.13

### 1. Install and configure

Clone the repository, then from the project root:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

Set `SECRET_KEY` in `.env`. You can generate one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 2. Create the database and start the server

```bash
python manage.py migrate
python manage.py seed_demo_data      # prints the demo passwords, so note them
python manage.py test                # optional: should end with OK
python manage.py runserver
```

Open http://127.0.0.1:8000/ for the marketplace and http://127.0.0.1:8000/admin/ for the admin.
If port 8000 is already taken, run `python manage.py runserver 8001` and use that port instead.

`seed_demo_data` creates three accounts:

- `admin`: a superuser with a few shop listings.
- `reader` and `bookworm`: members who own books, have listings open to trade, and have already exchanged
  swap offers.

It also loads 14 listings across 6 genres and all four conditions. The passwords are generated on each run
and **printed only to your console**, so no credentials live in the repository. Set `DEMO_PASSWORD` in
`.env` to use a fixed password instead, and pass `--reset` to wipe and rebuild the catalogue.

### 3. Try it out

- **Search:** search for "tolkien", tick a couple of conditions, and set a price range.
- **Swap:**
  1. Log in as `reader`, open **Trades** and accept or decline `bookworm`'s offer. Accepting takes a copy of
     each book out of stock.
  2. Open **Swap books**, pick a book and offer one of yours.
  3. Log in as `bookworm` to answer it.
- **Sell:** use **List a book** to post a listing; an invalid ISBN shows an error. Edit or delete it from
  **My listings**.
- **Buy:** add another member's book to your cart, check out, open the order and cancel it. The stock goes
  back up.
- **Admin:** log in as `admin` and try the listing, swap-offer and order actions in the admin.
- **JSON search:** open http://127.0.0.1:8000/books/api/?q=dune&condition=new

### Stopping and restarting

- Stop the server with `Ctrl+C`; leave the virtualenv with `deactivate`.
- Next time, run `source .venv/bin/activate` and `python manage.py runserver` from the project root.
- To start over, delete `db.sqlite3`, then run `python manage.py migrate` and
  `python manage.py seed_demo_data`.
- Lost the demo passwords? Run `python manage.py seed_demo_data` again; each run replaces them.

### Using PostgreSQL

Install the driver, then set `DATABASE_URL` in `.env` and migrate:

```bash
pip install "psycopg[binary]"
# .env: DATABASE_URL=postgres://booktrading:change-me@localhost:5432/booktrading
python manage.py migrate
```

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `SECRET_KEY not found` | `.env` is missing. Copy `.env.example` to `.env` and set `SECRET_KEY`. |
| "Please enter a correct username and password" | Use the passwords from your most recent `seed_demo_data` run. |
| `Error: That port is already in use` | Stop the other server, or run `python manage.py runserver 8001`. |
| Pages look unstyled | Bootstrap and the fonts load from CDNs, so check your internet connection. With `DEBUG=False`, run `collectstatic` and serve `staticfiles/`. |

## Search parameters

The listing search (`/`) and the JSON endpoint (`/books/api/`) accept the same query parameters:

| Parameter | Example | Effect |
| --- | --- | --- |
| `q` | `q=tolkien` | Case-insensitive match on title, author name or ISBN (hyphens ignored) |
| `condition` | `condition=new&condition=like_new` | Any of `new`, `like_new`, `good`, `fair` |
| `min_price`, `max_price` | `min_price=5&max_price=10` | Price range, inclusive |
| `genre` | `genre=3` | Genre ID |
| `in_stock` | `in_stock=on` | Only listings with copies left |
| `sort` | `sort=-price` | `title` (default), `author`, `price`, `-price`, `newest` |
| `page` | `page=2` | 12 results per page |

Invalid values are shown as form errors and left out of the query; the JSON endpoint returns `400` with
field errors instead. The swap browser at `/trading/` accepts `q` and a single `condition`.

```bash
curl "http://127.0.0.1:8000/books/api/?q=le%20guin&condition=like_new&condition=fair&max_price=10&sort=-price"
```

## Configuration

Settings are read from environment variables or `.env` via python-decouple, and nothing secret is
hard-coded.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | *(required)* | Django secret key |
| `DEBUG` | `False` | Development mode |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names |
| `CSRF_TRUSTED_ORIGINS` | *(empty)* | HTTPS origins allowed to submit forms |
| `DATABASE_URL` | SQLite file next to `manage.py` | Database connection URL, including credentials |
| `DATABASE_CONN_MAX_AGE` | `0` | Persistent connection lifetime in seconds |
| `DEMO_PASSWORD` | *(random)* | Fixed password for the `seed_demo_data` accounts |
| `CURRENCY_SYMBOL` | `€` | Symbol used when displaying prices |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | `False`, `0` | HTTPS hardening (applies when `DEBUG=False`) |

## Tests

```bash
python manage.py test
```

The suite of about 140 tests covers:

- search: the combined `Q` query, condition and price filters, validation, pagination and the JSON API;
- listing management: ownership rules, author matching and duplicate ISBNs across members;
- swaps: constraints, offer rules, accept/decline/withdraw permissions, stock changes, automatic declines
  and admin actions;
- the cart (stock limits, per-user isolation, no buying your own listing) and checkout (stock race with no
  partial updates, price snapshots, cancellation and restock);
- accounts, the shared core utilities and the seed command.

## Deploying

- Set `DEBUG=False`, a strong `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` and the
  HTTPS settings.
- Run `python manage.py migrate` and `python manage.py collectstatic`, then serve the project with a WSGI
  server such as gunicorn behind an HTTPS reverse proxy.
- Use `/health/` for load-balancer or uptime checks.
