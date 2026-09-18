from . import services


def trade_summary(request):
    """Number of unanswered offers on the signed-in user's books, for the navigation badge."""
    if not request.user.is_authenticated:
        return {}
    return {'pending_offer_count': services.pending_offer_count(request.user)}
