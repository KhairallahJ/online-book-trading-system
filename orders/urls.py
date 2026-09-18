from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    # Shopping cart
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/<int:book_id>/', views.add_to_cart, name='cart_add'),
    path('cart/items/<int:item_id>/update/', views.update_item, name='cart_update'),
    path('cart/items/<int:item_id>/remove/', views.remove_item, name='cart_remove'),

    # Checkout and order history
    path('', views.order_list, name='list'),
    path('checkout/', views.checkout, name='checkout'),
    path('<int:order_id>/', views.order_detail, name='detail'),
    path('<int:order_id>/cancel/', views.cancel_order, name='cancel'),
]
