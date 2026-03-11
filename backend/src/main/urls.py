from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# wagtail
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

# pygeoapi integration
from pygeoapi.django_ import urls as pygeoapi_urls

from api import urls as api_urls

urlpatterns = [
    # OpenAPI Schema
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # API
    path("api/", include(api_urls)),
    # Admin
    path("djadmin/", admin.site.urls),
    # OIDC
    path("oidc/", include("oidc_provider.urls", namespace="oidc_provider")),
    # Accounts
    path("account/", include("account.urls")),
    # pygeoapi endpoint
    path("geoapi/", include(pygeoapi_urls)),
    # wagtail document serving
    path("documents/", include(wagtaildocs_urls)),
    # wagtail admin and site
    path("dms/", include(wagtailadmin_urls)),
    path("", include(wagtail_urls)),
]
