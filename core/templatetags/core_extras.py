import zlib
from decimal import Decimal

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def currency(amount):
    """Format a price with the site currency, e.g. 12.5 -> €12.50."""
    if amount in (None, ''):
        return ''
    return f'{settings.CURRENCY_SYMBOL}{Decimal(str(amount)):,.2f}'


@register.filter
def cover_hue(text):
    """A stable colour hue (0-359) derived from text, used to tint the generated book covers."""
    return zlib.crc32(str(text).encode()) % 360


@register.filter
def cover_title_class(text):
    """A CSS class that shrinks cover titles whose longest word would not fit on one line."""
    longest = max((len(word) for word in str(text).split()), default=0)
    if longest > 11:
        return 'book-cover-very-long-words'
    if longest > 8:
        return 'book-cover-long-words'
    return ''
