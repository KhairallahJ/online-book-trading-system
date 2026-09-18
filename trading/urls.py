from django.urls import path

from . import views

app_name = 'trading'

urlpatterns = [
    path('', views.TradeableBookListView.as_view(), name='browse'),
    path('books/<int:book_id>/offer/', views.propose_trade, name='propose'),
    path('mine/', views.my_trades, name='my_trades'),
    path('<int:trade_id>/accept/', views.accept_trade, name='accept'),
    path('<int:trade_id>/decline/', views.decline_trade, name='decline'),
    path('<int:trade_id>/withdraw/', views.withdraw_trade, name='withdraw'),
]
