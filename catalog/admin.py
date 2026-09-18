from django.contrib import admin
from django.db.models import Count

from .models import Author, Book, Genre


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'book_count']
    search_fields = ['name']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(book_count=Count('books'))

    @admin.display(ordering='book_count', description='Books')
    def book_count(self, genre):
        return genre.book_count


class BookInline(admin.TabularInline):
    model = Book
    fields = ['title', 'isbn', 'genre', 'condition', 'price', 'stock', 'posted_by']
    autocomplete_fields = ['genre', 'posted_by']
    extra = 0
    show_change_link = True


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['name', 'book_count']
    search_fields = ['name']
    inlines = [BookInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(book_count=Count('books'))

    @admin.display(ordering='book_count', description='Books')
    def book_count(self, author):
        return author.book_count


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'genre', 'condition', 'price', 'stock', 'open_to_trade', 'posted_by', 'created_at']
    list_editable = ['price', 'stock', 'open_to_trade']
    list_filter = ['condition', 'open_to_trade', 'genre', 'created_at']
    list_select_related = ['author', 'genre', 'posted_by']
    search_fields = ['title', 'isbn', 'author__name', 'posted_by__username']
    autocomplete_fields = ['author', 'genre', 'posted_by']
    date_hierarchy = 'created_at'
    actions = ['mark_out_of_stock', 'withdraw_from_trading']

    @admin.action(description='Mark selected books as out of stock')
    def mark_out_of_stock(self, request, queryset):
        updated = queryset.update(stock=0)
        self.message_user(request, f'{updated} book(s) marked as out of stock.')

    @admin.action(description='Withdraw selected books from trading')
    def withdraw_from_trading(self, request, queryset):
        updated = queryset.update(open_to_trade=False)
        self.message_user(request, f'{updated} book(s) withdrawn from trading.')
