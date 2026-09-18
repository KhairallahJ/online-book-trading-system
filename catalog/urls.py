from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    # Home: searchable, filterable list of every listing
    path('', views.BookListView.as_view(), name='book_list'),

    # JSON search endpoint (same query parameters as the list page)
    path('books/api/', views.book_search_api, name='book_search_api'),

    # Members' own listings
    path('books/mine/', views.MyListingsView.as_view(), name='my_listings'),
    path('books/add/', views.BookCreateView.as_view(), name='create_book'),

    # A single listing and its owner/staff actions
    path('books/<int:book_id>/', views.book_detail, name='book_detail'),
    path('books/<int:book_id>/edit/', views.BookUpdateView.as_view(), name='edit_book'),
    path('books/<int:book_id>/delete/', views.BookDeleteView.as_view(), name='delete_book'),

    # Browse by genre or author
    path('genre/<str:genre_name>/', views.GenreBookListView.as_view(), name='genre_books'),
    path('authors/<int:author_id>/', views.author_detail, name='author_detail'),
]
