from django.conf import settings
from django.db import models
from django.urls import reverse


class TradeRequest(models.Model):
    """An offer to swap one of the requester's books for another member's listing."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        DECLINED = 'declined', 'Declined'

    # Referenced by app label, without reverse accessors, so the catalog stays unaware of trading.
    book_wanted  = models.ForeignKey('catalog.Book', on_delete=models.CASCADE, related_name='+')
    offered_book = models.ForeignKey('catalog.Book', on_delete=models.CASCADE, related_name='+')
    requester    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trade_requests')
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    message      = models.CharField(max_length=500, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['book_wanted', 'offered_book'],
                condition=models.Q(status='pending'),
                name='unique_pending_trade_offer',
                violation_error_message='This book has already been offered for that listing.',
            ),
            models.CheckConstraint(
                condition=~models.Q(book_wanted=models.F('offered_book')),
                name='trade_books_differ',
                violation_error_message='A book cannot be swapped for itself.',
            ),
        ]
        indexes = [
            # "Offers I sent" and "offers on my books" are both filtered by status.
            models.Index(fields=['requester', 'status'], name='trade_requester_status_idx'),
            models.Index(fields=['book_wanted', 'status'], name='trade_wanted_status_idx'),
        ]

    def __str__(self):
        return f"Trade #{self.pk}: {self.offered_book} for {self.book_wanted}"

    def get_absolute_url(self):
        return reverse('trading:my_trades')

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING
