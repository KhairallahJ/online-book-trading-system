from django.contrib import admin, messages

from . import services
from .models import TradeRequest


@admin.register(TradeRequest)
class TradeRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'book_wanted', 'owner', 'offered_book', 'requester', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    list_select_related = ['book_wanted__author', 'book_wanted__posted_by', 'offered_book__author', 'requester']
    search_fields = ['book_wanted__title', 'offered_book__title', 'requester__username']
    date_hierarchy = 'created_at'
    # Offers are made on the site, and status changes go through the trading services
    # so accepted swaps always update stock; only the message can be moderated here.
    readonly_fields = ['book_wanted', 'offered_book', 'requester', 'status', 'created_at', 'responded_at']
    actions = ['decline_selected']

    def has_add_permission(self, request):
        return False

    @admin.display(ordering='book_wanted__posted_by__username', description='Owner')
    def owner(self, trade):
        return trade.book_wanted.posted_by

    @admin.action(description='Decline selected pending offers')
    def decline_selected(self, request, queryset):
        declined = 0
        for trade in queryset.select_related('book_wanted'):
            try:
                services.decline_trade(trade, trade.book_wanted.posted_by)
                declined += 1
            except services.TradeError as error:
                self.message_user(request, f'Trade #{trade.pk}: {error}', level=messages.WARNING)
        self.message_user(request, f'{declined} offer(s) declined.')
