from django.contrib import admin
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import include, path, re_path
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
from .views import (
    DatasetDetailView,
    DatasetListView,
    HomeView,
    OrganizationDetailView,
    OrganizationListView,
    ResourceDetailView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("datasets/", DatasetListView.as_view(), name="dataset-list"),
    path("datasets/<slug:slug>/", DatasetDetailView.as_view(), name="dataset-detail"),
    path(
        "datasets/<slug:dataset_slug>/resources/<slug:resource_slug>/",
        ResourceDetailView.as_view(),
        name="resource-detail",
    ),
    path("organizations/", OrganizationListView.as_view(), name="organization-list"),
    path("organizations/<slug:slug>/", OrganizationDetailView.as_view(), name="organization-detail"),
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
