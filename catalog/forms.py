from django import forms

from core.forms import BootstrapFormMixin

from .models import Author, Book, Genre


class BookForm(BootstrapFormMixin, forms.ModelForm):
    """Create or edit a listing. The author is typed by name and matched (or added) on save."""

    author_name = forms.CharField(label='Author', max_length=200)

    class Meta:
        model = Book
        fields = ['title', 'author_name', 'genre', 'isbn', 'condition', 'price', 'stock', 'open_to_trade']
        help_texts = {'isbn': '10 or 13 digits, without spaces or hyphens.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.author_id:
            self.fields['author_name'].initial = self.instance.author.name

    def clean_author_name(self):
        return ' '.join(self.cleaned_data['author_name'].split())

    def save(self, commit=True):
        name = self.cleaned_data['author_name']
        author = Author.objects.filter(name__iexact=name).first()
        self.instance.author = author or Author.objects.create(name=name)
        return super().save(commit)


class BookSearchForm(BootstrapFormMixin, forms.Form):
    """Validates the catalogue's GET parameters; invalid fields are dropped rather than applied."""

    SORT_CHOICES = [
        ('title', 'Title (A-Z)'),
        ('author', 'Author (A-Z)'),
        ('price', 'Price: low to high'),
        ('-price', 'Price: high to low'),
        ('newest', 'Newest listings'),
    ]

    q = forms.CharField(
        label='Search',
        required=False,
        max_length=100,
        widget=forms.SearchInput(attrs={'placeholder': 'Title, author or ISBN'}),
    )
    condition = forms.MultipleChoiceField(
        choices=Book.Condition.choices, required=False, widget=forms.CheckboxSelectMultiple
    )
    genre = forms.ModelChoiceField(
        queryset=Genre.objects.order_by('name'), required=False, empty_label='All genres'
    )
    min_price = forms.DecimalField(label='Min price', required=False, min_value=0, decimal_places=2)
    max_price = forms.DecimalField(label='Max price', required=False, min_value=0, decimal_places=2)
    in_stock = forms.BooleanField(label='In stock only', required=False)
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False)

    def clean(self):
        cleaned_data = super().clean()
        low, high = cleaned_data.get('min_price'), cleaned_data.get('max_price')
        if low is not None and high is not None and low > high:
            self.add_error('max_price', 'Max price must be at least the min price.')
        return cleaned_data
