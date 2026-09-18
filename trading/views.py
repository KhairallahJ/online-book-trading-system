from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from catalog.search import search_books

from . import services
from .forms import TradeOfferForm, TradeSearchForm
from .models import TradeRequest

PAGE_SIZE = 12
TRADE_RELATIONS = (
    'requester', 'book_wanted__author', 'book_wanted__posted_by', 'offered_book__author', 'offered_book__posted_by',
)


def my_trades_url(box):
    return f"{reverse('trading:my_trades')}?box={box}"


class TradeableBookListView(ListView):
    """Books other members are willing to swap."""

    template_name = 'trading/browse.html'
    context_object_name = 'books'
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.form = TradeSearchForm(self.request.GET or None)
        filters = self.form.cleaned_data if self.form.is_valid() else {}
        return search_books(services.tradeable_books(self.request.user), **filters)

    def get_context_data(self, **kwargs):
        return super().get_context_data(form=self.form, **kwargs)


@login_required
def propose_trade(request, book_id):
    book = get_object_or_404(services.book_model().objects.select_related('author', 'posted_by'), pk=book_id)
    if book.posted_by_id == request.user.pk:
        messages.error(request, "You can't make an offer on your own listing.")
        return redirect(book)
    if not (book.open_to_trade and book.in_stock):
        messages.error(request, f'"{book.title}" is not available for swaps right now.')
        return redirect(book)

    form = TradeOfferForm(request.POST or None, requester=request.user, book_wanted=book)
    if request.method == 'POST' and form.is_valid():
        try:
            services.propose_trade(
                request.user, book, form.cleaned_data['offered_book'], form.cleaned_data['message']
            )
        except services.TradeError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'Your swap offer for "{book.title}" was sent to {book.posted_by}.')
            return redirect(my_trades_url('sent'))
    return render(request, 'trading/propose.html', {'book': book, 'form': form})


@login_required
def my_trades(request):
    """Offers received on the user's listings (default) or offers the user has sent."""
    box = 'sent' if request.GET.get('box') == 'sent' else 'received'
    trades = TradeRequest.objects.select_related(*TRADE_RELATIONS)
    if box == 'sent':
        trades = trades.filter(requester=request.user)
    else:
        trades = trades.filter(book_wanted__posted_by=request.user)
    page = Paginator(trades, 10).get_page(request.GET.get('page'))
    return render(request, 'trading/my_trades.html', {'box': box, 'trades': page.object_list, 'page_obj': page})


def _respond(request, trade_id, action, success_message):
    """Accept or decline an offer on one of the user's own listings."""
    trade = get_object_or_404(
        TradeRequest.objects.select_related(*TRADE_RELATIONS), pk=trade_id, book_wanted__posted_by=request.user
    )
    try:
        action(trade, request.user)
    except services.TradeError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success_message.format(trade=trade))
    return redirect(my_trades_url('received'))


@login_required
@require_POST
def accept_trade(request, trade_id):
    return _respond(
        request, trade_id, services.accept_trade,
        'Swap agreed: "{trade.offered_book.title}" for "{trade.book_wanted.title}". '
        'Arrange the exchange with {trade.requester}.',
    )


@login_required
@require_POST
def decline_trade(request, trade_id):
    return _respond(request, trade_id, services.decline_trade, 'Offer from {trade.requester} declined.')


@login_required
@require_POST
def withdraw_trade(request, trade_id):
    trade = get_object_or_404(TradeRequest.objects.select_related('book_wanted'), pk=trade_id, requester=request.user)
    try:
        services.withdraw_trade(trade, request.user)
    except services.TradeError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f'Your offer for "{trade.book_wanted.title}" was withdrawn.')
    return redirect(my_trades_url('sent'))
