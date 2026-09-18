from django.db.models import Q

# Sort keys accepted from the query string, mapped to model ordering (with a stable tie-breaker).
SORT_ORDERING = {
    'title': ('title', 'pk'),
    'price': ('price', 'pk'),
    '-price': ('-price', 'pk'),
    'author': ('author__name', 'pk'),
    'newest': ('-created_at', '-pk'),
}


def text_query(q):
    """Case-insensitive match on title, author name or ISBN."""
    match = Q(title__icontains=q) | Q(author__name__icontains=q)
    # ISBNs are stored without separators, so ignore hyphens/spaces the user typed.
    isbn = q.replace('-', '').replace(' ', '')
    if isbn:
        match |= Q(isbn__icontains=isbn)
    return match


def build_search_query(*, q='', condition=(), min_price=None, max_price=None, genre=None, in_stock=False):
    """Combine the (all optional) search criteria into a single Q object; unset criteria are left out."""
    query = Q()
    q = q.strip()
    if q:
        query &= text_query(q)
    if condition:
        query &= Q(condition__in=condition)
    if min_price is not None:
        query &= Q(price__gte=min_price)
    if max_price is not None:
        query &= Q(price__lte=max_price)
    if genre is not None:
        query &= Q(genre=genre)
    if in_stock:
        query &= Q(stock__gt=0)
    return query


def search_books(queryset, *, sort='', **criteria):
    """Apply the catalogue's search criteria (see build_search_query) and sort order to a Book queryset."""
    ordering = SORT_ORDERING.get(sort, SORT_ORDERING['title'])
    return queryset.filter(build_search_query(**criteria)).order_by(*ordering)
