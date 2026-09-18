from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import OwnerOrStaffRequiredMixin

from .forms import BookForm, BookSearchForm
from .models import Author, Book, Genre
from .search import search_books

PAGE_SIZE = 12
LISTING_RELATIONS = ('author', 'genre', 'posted_by')


def get_search_results(data):
    """Validate search parameters and return (form, filtered books); invalid fields are ignored."""
    form = BookSearchForm(data or None)
    filters = {}
    if form.is_bound:
        form.is_valid()  # populates cleaned_data with the fields that did validate
        filters = form.cleaned_data
    books = search_books(Book.objects.select_related(*LISTING_RELATIONS), **filters)
    return form, books


class BookListView(ListView):
    template_name = 'catalog/book_list.html'
    context_object_name = 'books'
    paginate_by = PAGE_SIZE

    def get_search_data(self):
        return self.request.GET

    def get_queryset(self):
        self.form, books = get_search_results(self.get_search_data())
        return books

    def get_context_data(self, **kwargs):
        return super().get_context_data(form=self.form, **kwargs)


class GenreBookListView(BookListView):
    """The catalogue pre-filtered to one genre (reached from the navigation menu)."""

    def get_search_data(self):
        self.genre = get_object_or_404(Genre, name__iexact=self.kwargs['genre_name'])
        data = self.request.GET.copy()
        data['genre'] = self.genre.pk
        return data

    def get_context_data(self, **kwargs):
        return super().get_context_data(genre=self.genre, **kwargs)


@require_GET
def book_search_api(request):
    """JSON version of the catalogue search, accepting the same query parameters."""
    form, books = get_search_results(request.GET)
    if form.is_bound and not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    page = Paginator(books, PAGE_SIZE).get_page(request.GET.get('page'))
    return JsonResponse({
        'count': page.paginator.count,
        'page': page.number,
        'num_pages': page.paginator.num_pages,
        'results': [
            {
                'id': book.pk,
                'title': book.title,
                'author': book.author.name,
                'genre': book.genre.name,
                'isbn': book.isbn,
                'condition': book.condition,
                'price': str(book.price),
                'stock': book.stock,
                'open_to_trade': book.open_to_trade,
                'posted_by': book.posted_by.get_username(),
                'url': request.build_absolute_uri(book.get_absolute_url()),
            }
            for book in page
        ],
    })


def book_detail(request, book_id):
    book = get_object_or_404(Book.objects.select_related(*LISTING_RELATIONS), pk=book_id)
    return render(request, 'catalog/book_detail.html', {
        'book': book,
        'can_edit': book.can_edit(request.user),
        'is_own_listing': book.posted_by_id == request.user.pk,
    })


def author_detail(request, author_id):
    author = get_object_or_404(Author, pk=author_id)
    books = author.books.select_related(*LISTING_RELATIONS)
    return render(request, 'catalog/author_detail.html', {'author': author, 'books': books})


class MyListingsView(LoginRequiredMixin, ListView):
    template_name = 'catalog/my_listings.html'
    context_object_name = 'books'
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        return (
            Book.objects.filter(posted_by=self.request.user)
            .select_related(*LISTING_RELATIONS)
            .order_by('-created_at', '-pk')
        )


class BookCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Book
    form_class = BookForm
    success_message = '"%(title)s" is now listed.'

    def form_valid(self, form):
        form.instance.posted_by = self.request.user
        return super().form_valid(form)


class BookUpdateView(OwnerOrStaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Book
    queryset = Book.objects.select_related('author')
    form_class = BookForm
    pk_url_kwarg = 'book_id'
    success_message = '"%(title)s" was updated.'


class BookDeleteView(OwnerOrStaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Book
    pk_url_kwarg = 'book_id'
    success_url = reverse_lazy('catalog:my_listings')

    def get_success_message(self, cleaned_data):
        return f'"{self.object.title}" was removed from the catalogue.'
