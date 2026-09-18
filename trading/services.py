"""Trade rules: who may offer what, and what happens when an offer is accepted.

Views and the admin go through these functions rather than changing TradeRequest rows directly.
"""
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import TradeRequest


class TradeError(Exception):
    """A trade action that isn't allowed, e.g. offering a book you don't own."""


def book_model():
    """The catalogue's Book model, resolved through the FK rather than imported from another app."""
    return TradeRequest._meta.get_field('book_wanted').related_model


def tradeable_books(user=None):
    """Listings other members can make offers on: open to trade, in stock and not the user's own."""
    books = book_model().objects.filter(open_to_trade=True, stock__gt=0)
    if user is not None and user.is_authenticated:
        books = books.exclude(posted_by=user)
    return books.select_related('author', 'genre', 'posted_by')


def offerable_books(user):
    """The user's own in-stock listings, any of which can be put up in exchange."""
    return book_model().objects.filter(posted_by=user, stock__gt=0).select_related('author').order_by('title', 'pk')


def check_offer(requester, book_wanted, offered_book):
    """Raise TradeError unless ``requester`` may offer ``offered_book`` in exchange for ``book_wanted``."""
    if book_wanted.posted_by_id == requester.pk:
        raise TradeError("You can't make an offer on your own listing.")
    if not book_wanted.open_to_trade:
        raise TradeError(f'"{book_wanted.title}" is not open to swaps.')
    if book_wanted.stock < 1:
        raise TradeError(f'"{book_wanted.title}" is no longer available.')
    if offered_book.posted_by_id != requester.pk:
        raise TradeError('You can only offer books from your own listings.')
    if offered_book.stock < 1:
        raise TradeError(f'"{offered_book.title}" is out of stock, so it can\'t be offered.')
    already_offered = TradeRequest.objects.filter(
        book_wanted=book_wanted, offered_book=offered_book, status=TradeRequest.Status.PENDING
    )
    if already_offered.exists():
        raise TradeError(f'You have already offered "{offered_book.title}" for this book.')


@transaction.atomic
def propose_trade(requester, book_wanted, offered_book, message=''):
    check_offer(requester, book_wanted, offered_book)
    return TradeRequest.objects.create(
        requester=requester, book_wanted=book_wanted, offered_book=offered_book, message=message
    )


def _locked_pending(trade):
    trade = TradeRequest.objects.select_for_update().get(pk=trade.pk)
    if not trade.is_pending:
        raise TradeError(f'This offer has already been {trade.get_status_display().lower()}.')
    return trade


@transaction.atomic
def accept_trade(trade, owner):
    """Accept an offer on ``owner``'s listing: one copy of each book changes hands."""
    trade = _locked_pending(trade)
    Book = book_model()
    # Lock both listings so a concurrent sale or swap can't take the same copy.
    books = Book.objects.select_for_update().in_bulk([trade.book_wanted_id, trade.offered_book_id])
    wanted, offered = books.get(trade.book_wanted_id), books.get(trade.offered_book_id)
    if wanted is None or wanted.posted_by_id != owner.pk:
        raise TradeError('Only the owner of the listing can accept this offer.')
    if offered is None or offered.posted_by_id != trade.requester_id:
        raise TradeError('The offered book is no longer listed by the member who offered it.')
    for book in (wanted, offered):
        if book.stock < 1:
            raise TradeError(f'"{book.title}" is no longer in stock, so this swap can\'t go ahead.')

    Book.objects.filter(pk__in=[wanted.pk, offered.pk]).update(stock=F('stock') - 1)
    now = timezone.now()
    trade.status = TradeRequest.Status.ACCEPTED
    trade.responded_at = now
    trade.save(update_fields=['status', 'responded_at'])

    # Other pending offers that relied on a copy that has just run out can't happen any more.
    sold_out = [book.pk for book in (wanted, offered) if book.stock == 1]
    if sold_out:
        TradeRequest.objects.filter(status=TradeRequest.Status.PENDING).filter(
            Q(book_wanted__in=sold_out) | Q(offered_book__in=sold_out)
        ).update(status=TradeRequest.Status.DECLINED, responded_at=now)
    return trade


@transaction.atomic
def decline_trade(trade, owner):
    trade = _locked_pending(trade)
    if trade.book_wanted.posted_by_id != owner.pk:
        raise TradeError('Only the owner of the listing can decline this offer.')
    trade.status = TradeRequest.Status.DECLINED
    trade.responded_at = timezone.now()
    trade.save(update_fields=['status', 'responded_at'])
    return trade


@transaction.atomic
def withdraw_trade(trade, requester):
    """Take back an offer that hasn't been answered yet (the request is removed)."""
    trade = _locked_pending(trade)
    if trade.requester_id != requester.pk:
        raise TradeError('Only the member who made this offer can withdraw it.')
    trade.delete()


def pending_offer_count(user):
    """Unanswered offers on the user's listings, for the navigation badge."""
    return TradeRequest.objects.filter(book_wanted__posted_by=user, status=TradeRequest.Status.PENDING).count()
