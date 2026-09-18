from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import cart as cart_services
from . import services
from .forms import AddToCartForm, CheckoutForm, UpdateQuantityForm
from .models import CartItem, Order


# Shopping cart

@login_required
def cart_detail(request):
    cart = cart_services.get_cart(request.user)
    items = cart.items.select_related('book__author')
    return render(request, 'orders/cart_detail.html', {
        'items': items,
        'total': sum((item.subtotal for item in items), Decimal('0.00')),
    })


@login_required
@require_POST
def add_to_cart(request, book_id):
    book = get_object_or_404(cart_services.book_model(), pk=book_id)
    form = AddToCartForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a quantity between 1 and 99.')
        return redirect(book)
    try:
        cart_services.add_book(cart_services.get_cart(request.user), book, form.cleaned_data['quantity'])
    except cart_services.CartError as error:
        messages.error(request, str(error))
        return redirect(book)
    messages.success(request, f'Added "{book.title}" to your cart.')
    return redirect('orders:cart')


@login_required
@require_POST
def update_item(request, item_id):
    item = get_object_or_404(CartItem.objects.select_related('book'), pk=item_id, cart__user=request.user)
    form = UpdateQuantityForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a quantity between 0 and 99.')
    else:
        try:
            if cart_services.set_quantity(item, form.cleaned_data['quantity']) is None:
                messages.success(request, f'Removed "{item.book.title}" from your cart.')
        except cart_services.CartError as error:
            messages.error(request, str(error))
    return redirect('orders:cart')


@login_required
@require_POST
def remove_item(request, item_id):
    item = get_object_or_404(CartItem.objects.select_related('book'), pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, f'Removed "{item.book.title}" from your cart.')
    return redirect('orders:cart')


# Checkout and order history

@login_required
def checkout(request):
    cart = cart_services.get_cart(request.user)
    lines = cart_services.get_cart_lines(cart.id)
    if not lines:
        messages.warning(request, "Your cart is empty, add items before checking out.")
        return redirect("orders:cart")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                order = services.place_order(request.user, **form.cleaned_data)
            except services.CheckoutError as error:
                messages.error(request, str(error))
                return redirect("orders:cart")
            messages.success(request, f"Thank you! Order {order.number} has been placed.")
            return redirect(order)
    else:
        user = request.user
        form = CheckoutForm(initial={"full_name": user.get_full_name(), "email": user.email})

    return render(request, "orders/checkout.html", {
        "form": form,
        "lines": lines,
        "total": sum(line.subtotal for line in lines),
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    page = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"orders": page.object_list, "page_obj": page})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=order_id, user=request.user)
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    try:
        services.cancel_order(order)
    except services.CheckoutError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Order {order.number} has been cancelled.")
    return redirect(order)
