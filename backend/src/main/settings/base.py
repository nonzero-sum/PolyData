import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.utils import get_random_secret_key
from django.urls import reverse_lazy
from django.utils.csp import CSP
from django.utils.translation import gettext_lazy as _
from pygeoapi.openapi import get_oas
from pygeoapi.util import get_api_rules

######################################################################
# Utils
######################################################################

def _clean_host(value):
    if not value:
        return ""
    # strip scheme and trailing slashes
    host = value.replace("http://", "").replace("https://", "").strip().strip("/")
    # drop port if present (e.g. localhost:8000 -> localhost)
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


def _env_list(name, default=None):
    value = os.environ.get(name, "")
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or (default or [])


def _env_first(*names, default=None):
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return default


def _env_bbox(name, default=None):
    default = default or [-180.0, -90.0, 180.0, 90.0]
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default

    try:
        values = [float(item.strip()) for item in raw_value.split(",")]
    except ValueError:
        return default

    if len(values) not in (4, 6):
        return default

    return values


def _module_available(module_name):
    return importlib.util.find_spec(module_name) is not None


def _normalize_url_path(value, default="/"):
    normalized_value = (value or "").strip()
    if not normalized_value:
        normalized_value = default

    stripped_value = normalized_value.strip("/")
    if not stripped_value:
        return "/"

    return f"/{stripped_value}"


def _join_base_url(base_url, path):
    normalized_base_url = (base_url or "").strip().rstrip("/")
    normalized_path = _normalize_url_path(path, default="/")
    if normalized_path == "/":
        return normalized_base_url or "/"
    return f"{normalized_base_url}{normalized_path}"

######################################################################
# General
######################################################################

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", get_random_secret_key())

DEBUG = str(os.environ.get("DEBUG", "true")).lower() in ("1", "true", "yes", "on")

SITE_URL = os.environ.get("DJANGO_URL", "http://localhost").strip()
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost").strip()

ALLOWED_HOSTS = [
    host
    for host in [
        _clean_host(SITE_URL),
        _clean_host(FRONTEND_URL),
        *[_clean_host(host) for host in os.environ.get("ALLOWED_HOSTS", "").split(",")],
    ]
    if host
]

CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in [
        SITE_URL.strip().rstrip("/"),
        FRONTEND_URL.strip().rstrip("/"),
        *[
            origin.strip().rstrip("/")
            for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
        ],
    ]
    if origin
]

WSGI_APPLICATION = "main.wsgi.application"

ROOT_URLCONF = "main.urls"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

######################################################################
# Security

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "img-src": [CSP.SELF, "https:"],
}

######################################################################
# Apps
######################################################################
INSTALLED_APPS = [
    # Wagtail CMS (must come before django.contrib.admin)
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.routable_page",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",  # core search backend
    "wagtail.admin",
    "wagtail",
    # extras needed by Wagtail
    "taggit",
    "django.contrib.postgres",
    # Django Contrib
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # DRF
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Pygeoapi
    "pygeoapi",
    # Auth
    "account",
    "oidc_provider",
    # PolyData Apps
    "main", # Main
    "ingestion", # Ingestion
    "catalog", # Data Catalog 
]

if DEBUG:
    INSTALLED_APPS += [
        "whitenoise.runserver_nostatic",
    ]

######################################################################
# Middleware
######################################################################
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "catalog.middleware.PygeoapiBootstrapMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

######################################################################
# Templates
######################################################################
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

######################################################################
# Database
######################################################################

GDAL_LIBRARY_PATH = os.environ.get("GDAL_LIBRARY_PATH", "/usr/lib/libgdal.so")
GEOS_LIBRARY_PATH = os.environ.get("GEOS_LIBRARY_PATH", "/usr/lib/libgeos_c.so")

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "USER": _env_first("POSTGRES_USER", "DB_USER"),
        "PASSWORD": _env_first("POSTGRES_PASSWORD", "DB_PASSWORD"),
        "NAME": _env_first("POSTGRES_DB", "DB_NAME", "DB_DATABASE"),
        "HOST": _env_first("POSTGRES_HOST", "DB_HOST"),
        "PORT": _env_first("POSTGRES_PORT", "DB_PORT"),
        "TEST": {
            "NAME": "test",
        },
    }
}

RESOURCE_DATA_SCHEMA = os.environ.get("RESOURCE_DATA_SCHEMA", "resource_data").strip() or "resource_data"

######################################################################
# Authentication
######################################################################
AUTH_USER_MODEL = "account.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_URL = "/account/login/"

OIDC_USERINFO = "main.settings.oidc.userinfo"

# OIDC_EXTRA_SCOPE_CLAIMS = 'main.settings.oidc.CustomScopeClaims'

######################################################################
# Internationalization
######################################################################
LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

######################################################################
# Wagtail
######################################################################
WAGTAIL_SITE_NAME = "PolyData Portal"
WAGTAILADMIN_BASE_URL = SITE_URL
WAGTAILDOCS_DOCUMENT_FORM_BASE = "catalog.forms.CatalogDocumentForm"

######################################################################
# PygeoAPI
######################################################################


def _split_schema_qualified_table_name(table_name, default_schema=None):
    normalized_table_name = (table_name or "").strip()
    normalized_default_schema = (default_schema or RESOURCE_DATA_SCHEMA).strip() or RESOURCE_DATA_SCHEMA

    if "." not in normalized_table_name:
        return normalized_default_schema, normalized_table_name

    schema_name, unqualified_table_name = normalized_table_name.split(".", 1)
    return schema_name.strip() or normalized_default_schema, unqualified_table_name.strip()

def _build_pygeoapi_resources():
    table_name = os.environ.get("PYGEOAPI_TABLE", "").strip()
    if not table_name:
        return {}

    table_schema, provider_table_name = _split_schema_qualified_table_name(table_name)

    collection_name = os.environ.get("PYGEOAPI_COLLECTION_NAME", "").strip()
    if not collection_name:
        collection_name = provider_table_name

    collection_title = os.environ.get(
        "PYGEOAPI_COLLECTION_TITLE", collection_name.replace("_", " ").title()
    ).strip()
    collection_description = os.environ.get(
        "PYGEOAPI_COLLECTION_DESCRIPTION",
        f"Features from the {table_name} PostGIS table.",
    ).strip()

    provider = {
        "type": "feature",
        "name": "PostgreSQL",
        "data": {
            "host": _env_first("POSTGRES_HOST", "DB_HOST", default="127.0.0.1"),
            "port": _env_first("POSTGRES_PORT", "DB_PORT", default="5432"),
            "dbname": _env_first("POSTGRES_DB", "DB_NAME", "DB_DATABASE", default="postgres"),
            "user": _env_first("POSTGRES_USER", "DB_USER", default="postgres"),
            "password": _env_first("POSTGRES_PASSWORD", "DB_PASSWORD", default=""),
            "search_path": _env_list(
                "PYGEOAPI_DB_SEARCH_PATH",
                default=[table_schema, "public"],
            ),
        },
        "table": provider_table_name,
        "id_field": os.environ.get("PYGEOAPI_ID_FIELD", "id"),
        "geom_field": os.environ.get("PYGEOAPI_GEOM_FIELD", "geom"),
    }

    time_field = os.environ.get("PYGEOAPI_TIME_FIELD", "").strip()
    title_field = os.environ.get("PYGEOAPI_TITLE_FIELD", "").strip()
    resource_crs = _env_list(
        "PYGEOAPI_CRS",
        default=["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
    )
    storage_crs = os.environ.get(
        "PYGEOAPI_STORAGE_CRS", "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
    ).strip()

    if time_field:
        provider["time_field"] = time_field
    if title_field:
        provider["title_field"] = title_field
    if resource_crs:
        provider["crs"] = resource_crs
        provider["storage_crs"] = storage_crs or resource_crs[0]

    resource = {
        "type": "collection",
        "title": collection_title,
        "description": collection_description,
        "keywords": _env_list(
            "PYGEOAPI_COLLECTION_KEYWORDS", default=["postgis", "polydata"]
        ),
        "extents": {
            "spatial": {
                "bbox": _env_bbox("PYGEOAPI_COLLECTION_BBOX"),
                "crs": resource_crs[0],
            }
        },
        "providers": [provider],
    }

    return {collection_name: resource}


def _build_pygeoapi_config():
    site_parts = urlsplit(SITE_URL if "://" in SITE_URL else f"http://{SITE_URL}")
    bind_host = os.environ.get("DJANGO_HOST", "").strip() or "0.0.0.0"
    bind_port = int(os.environ.get("DJANGO_PORT") or site_parts.port or 8000)
    service_name = os.environ.get("PYGEOAPI_TITLE", "PolyData GeoAPI").strip()
    pygeoapi_base_path = _normalize_url_path(
        os.environ.get("PYGEOAPI_BASE_PATH", "/geoapi"),
        default="/geoapi",
    )
    service_url = (
        os.environ.get("PYGEOAPI_URL", "").strip()
        or _join_base_url(SITE_URL or "http://localhost:8000", pygeoapi_base_path)
    )
    map_url = os.environ.get(
        "PYGEOAPI_MAP_URL",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    ).strip()
    map_attribution = os.environ.get(
        "PYGEOAPI_MAP_ATTRIBUTION",
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    ).strip()
    default_items_limit = max(int(os.environ.get("PYGEOAPI_DEFAULT_ITEMS", "10")), 1)
    max_items_limit = max(
        int(os.environ.get("PYGEOAPI_MAX_ITEMS", str(default_items_limit))),
        default_items_limit,
    )

    return {
        "server": {
            "bind": {
                "host": bind_host,
                "port": bind_port,
            },
            "url": f"{service_url}/",
            "mimetype": "application/json; charset=UTF-8",
            "encoding": "utf-8",
            "language": "en-US",
            "gzip": _env_bool("PYGEOAPI_GZIP", default=False),
            "cors": _env_bool("PYGEOAPI_CORS", default=False),
            "pretty_print": _env_bool("PYGEOAPI_PRETTY_PRINT", default=DEBUG),
            "admin": _env_bool("PYGEOAPI_ADMIN", default=False),
            "map": {
                "url": map_url,
                "attribution": map_attribution,
            },
            "limits": {
                "default_items": default_items_limit,
                "max_items": max_items_limit,
            },
        },
        "logging": {
            "level": os.environ.get(
                "PYGEOAPI_LOG_LEVEL", "DEBUG" if DEBUG else "ERROR"
            )
        },
        "metadata": {
            "identification": {
                "title": service_name,
                "description": os.environ.get(
                    "PYGEOAPI_DESCRIPTION",
                    "OGC API endpoint for PolyData geospatial resources.",
                ),
                "keywords": _env_list(
                    "PYGEOAPI_KEYWORDS", default=["geospatial", "api", "polydata"]
                ),
                "keywords_type": os.environ.get(
                    "PYGEOAPI_KEYWORDS_TYPE", "theme"
                ),
                "terms_of_service": os.environ.get(
                    "PYGEOAPI_TERMS_OF_SERVICE", service_url
                ),
                "url": os.environ.get("PYGEOAPI_METADATA_URL", service_url),
            },
            "license": {
                "name": os.environ.get("PYGEOAPI_LICENSE_NAME", "Proprietary"),
                "url": os.environ.get("PYGEOAPI_LICENSE_URL", service_url),
            },
            "provider": {
                "name": os.environ.get("PYGEOAPI_PROVIDER_NAME", "PolyData"),
                "url": os.environ.get("PYGEOAPI_PROVIDER_URL", service_url),
            },
            "contact": {
                "name": os.environ.get("PYGEOAPI_CONTACT_NAME", "PolyData Admin"),
                "email": os.environ.get(
                    "PYGEOAPI_CONTACT_EMAIL",
                    os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@polydata.com"),
                ),
                "role": os.environ.get("PYGEOAPI_CONTACT_ROLE", "pointOfContact"),
            },
        },
        "resources": _build_pygeoapi_resources(),
    }

PYGEOAPI_CONFIG = _build_pygeoapi_config()
API_RULES = get_api_rules(PYGEOAPI_CONFIG)
OPENAPI_DOCUMENT = get_oas(PYGEOAPI_CONFIG)
APPEND_SLASH = not API_RULES.strict_slashes

CORS_ALLOWED_ORIGINS = [
    origin
    for origin in [
        FRONTEND_URL.strip().rstrip("/"),
        *[
            origin.strip().rstrip("/")
            for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
        ],
    ]
    if origin
]
CORS_ALLOW_CREDENTIALS = True

######################################################################
# Staticfiles
######################################################################

STATIC_ROOT = BASE_DIR / "static"
STATIC_URL = "/static/"

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

######################################################################
# Storages
######################################################################

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

######################################################################
# Caches
######################################################################

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("VALKEY_URL", "redis://127.0.0.1:6379"),
    }
}

######################################################################
# Rest Framework
######################################################################
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

######################################################################
# Unfold
######################################################################
UNFOLD = {
    "SITE_HEADER": _("polydata"),
    "SITE_TITLE": _("polydata Admin"),
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Navigation"),
                "separator": False,
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:account_user_changelist"),
                    },
                    {
                        "title": _("Groups"),
                        "icon": "label",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}

######################################################################
# Print Settings
######################################################################

if DEBUG:
    print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
    print(f"CSRF_TRUSTED_ORIGINS: {CSRF_TRUSTED_ORIGINS}")
    print(f"DJANGO_URL: {SITE_URL}")
    print(f"FRONTEND_URL: {FRONTEND_URL}")
    print(f"WSGI_APPLICATION: {WSGI_APPLICATION}")
    print(f"ROOT_URLCONF: {ROOT_URLCONF}")
    print(f"DEFAULT_AUTO_FIELD: {DEFAULT_AUTO_FIELD}")
    print(f"INSTALLED_APPS: {INSTALLED_APPS}")
    print(f"MIDDLEWARE: {MIDDLEWARE}")
    print(f"TEMPLATES: {TEMPLATES}")
    print(f"DATABASES: {DATABASES}")
    print(f"AUTH_USER_MODEL: {AUTH_USER_MODEL}")
    print(f"LOGIN_URL: {LOGIN_URL}")
    print(f"LANGUAGE_CODE: {LANGUAGE_CODE}")
    print(f"TIME_ZONE: {TIME_ZONE}")
    print(f"USE_I18N: {USE_I18N}")
    print(f"USE_TZ: {USE_TZ}")
    print(f"STATIC_ROOT: {STATIC_ROOT}")
    print(f"STATIC_URL: {STATIC_URL}")
    print(f"MEDIA_ROOT: {MEDIA_ROOT}")
    print(f"PYGEOAPI_CONFIG: {PYGEOAPI_CONFIG}")
