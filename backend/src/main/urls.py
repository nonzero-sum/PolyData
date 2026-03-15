from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import AllowAny

# wagtail
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

# pygeoapi integration
from pygeoapi.django_ import urls as pygeoapi_urls

from api import urls as api_urls

urlpatterns = [
    # OpenAPI Schema
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]),
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema", permission_classes=[AllowAny]),
    ),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    # API
    path("api/", include(api_urls)),
    # Admin
    path("djadmin/", admin.site.urls),
    # OIDC
    path("oidc/", include("oidc_provider.urls", namespace="oidc_provider")),
    # Accounts
    path("account/", include("account.urls")),
    # pygeoapi static assets
    re_path(r"^geoapi/static/(?P<path>.*)$", staticfiles_serve),
    # pygeoapi endpoint
    path("geoapi/", include(pygeoapi_urls)),
    # wagtail document serving
    path("documents/", include(wagtaildocs_urls)),
    # wagtail admin and site
    path("dms/", include(wagtailadmin_urls)),
    path("", include(wagtail_urls)),
]

if settings.DEBUG and not getattr(settings, "USE_S3_STORAGE", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
