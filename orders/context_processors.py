from . import cart


def cart_summary(request):
    """Number of items in the signed-in user's cart, for the navigation badge."""
    if not request.user.is_authenticated:
        return {}
    return {'cart_item_count': cart.item_count(request.user)}
