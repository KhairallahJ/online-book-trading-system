from django.contrib import admin, messages
from django.utils import timezone

from . import services
from .models import Cart, CartItem, Order, OrderItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ['book']
    readonly_fields = ['added_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'item_count', 'total', 'updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [CartItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('items__book')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ['book', 'title', 'unit_price', 'quantity', 'subtotal']
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['number', 'user', 'full_name', 'status', 'total', 'created_at']
    list_filter = ['status', 'created_at']
    list_select_related = ['user']
    search_fields = ['id', 'user__username', 'full_name', 'email']
    date_hierarchy = 'created_at'
    # Status changes go through the actions below so cancellations always restock.
    readonly_fields = ['user', 'status', 'total', 'created_at', 'updated_at']
    inlines = [OrderItemInline]
    actions = ['mark_shipped', 'cancel_and_restock']

    def has_add_permission(self, request):
        # Orders are only created through checkout.
        return False

    @admin.display(ordering='pk', description='Order')
    def number(self, order):
        return order.number

    @admin.action(description='Mark selected orders as shipped')
    def mark_shipped(self, request, queryset):
        updated = queryset.filter(status=Order.Status.PLACED).update(
            status=Order.Status.SHIPPED, updated_at=timezone.now()
        )
        self.message_user(request, f'{updated} order(s) marked as shipped.')

    @admin.action(description='Cancel selected orders and restock their books')
    def cancel_and_restock(self, request, queryset):
        cancelled = 0
        for order in queryset:
            try:
                services.cancel_order(order)
                cancelled += 1
            except services.CheckoutError as error:
                self.message_user(request, str(error), level=messages.WARNING)
        self.message_user(request, f'{cancelled} order(s) cancelled and restocked.')
