from django.contrib import admin
from django.urls import include, path

# Each app owns its URLconf and is mounted under its own namespace (catalog:book_detail, trading:browse, ...).
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls", namespace="core")),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("trading/", include("trading.urls", namespace="trading")),
    path("orders/", include("orders.urls", namespace="orders")),
    path("", include("catalog.urls", namespace="catalog")),
]
