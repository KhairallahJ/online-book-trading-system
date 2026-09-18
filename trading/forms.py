from django import forms

from core.forms import BootstrapFormMixin
from core.templatetags.core_extras import currency

from . import services
from .models import TradeRequest


class TradeOfferForm(BootstrapFormMixin, forms.ModelForm):
    """Pick one of your own listings to offer in exchange for ``book_wanted``."""

    class Meta:
        model = TradeRequest
        fields = ['offered_book', 'message']
        labels = {'offered_book': 'Your book to swap', 'message': 'Message to the owner (optional)'}
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, requester, book_wanted, **kwargs):
        super().__init__(*args, **kwargs)
        self.requester = requester
        self.book_wanted = book_wanted
        field = self.fields['offered_book']
        field.queryset = services.offerable_books(requester)
        field.empty_label = 'Choose one of your books'
        field.label_from_instance = lambda book: (
            f'{book.title} ({book.get_condition_display()}, {currency(book.price)})'
        )

    def clean(self):
        cleaned_data = super().clean()
        offered_book = cleaned_data.get('offered_book')
        if offered_book is not None:
            try:
                services.check_offer(self.requester, self.book_wanted, offered_book)
            except services.TradeError as error:
                raise forms.ValidationError(str(error))
        return cleaned_data


class TradeSearchForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label='Search',
        required=False,
        max_length=100,
        widget=forms.SearchInput(attrs={'placeholder': 'Title, author or ISBN'}),
    )
    condition = forms.ChoiceField(
        choices=[('', 'Any condition')] + services.book_model().Condition.choices, required=False
    )

    def clean_condition(self):
        # search_books takes a collection of conditions.
        condition = self.cleaned_data['condition']
        return [condition] if condition else []
