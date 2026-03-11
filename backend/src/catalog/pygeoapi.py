import os

from django.conf import settings
from django.db import OperationalError, ProgrammingError

from pygeoapi.openapi import get_oas


def _resource_bbox(resource):
    bbox = resource.bbox
    if isinstance(bbox, list) and len(bbox) in (4, 6):
        return bbox
    return [-180.0, -90.0, 180.0, 90.0]


def _resource_keywords(resource):
    tags = resource.resource.dataset.tags if isinstance(resource.resource.dataset.tags, list) else []
    keywords = [*tags, resource.resource.resource_kind, resource.resource.storage_kind]
    return [keyword for keyword in keywords if keyword]


def build_pygeoapi_resources_from_catalog():
    from .models import ResourceTable

    resources = {}
    queryset = (
        ResourceTable.objects.select_related("resource", "resource__dataset")
        .filter(
            ogc_api_enabled=True,
        )
        .exclude(table_name="")
        .exclude(geometry_field="")
    )

    for resource in queryset:
        resources[resource.collection_name] = {
            "type": "collection",
            "title": resource.layer_name or resource.resource.title,
            "description": resource.resource.description
            or resource.resource.dataset.description
            or f"Collection for {resource.resource.title}.",
            "keywords": _resource_keywords(resource),
            "extents": {
                "spatial": {
                    "bbox": _resource_bbox(resource),
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                }
            },
            "providers": [
                {
                    "type": "feature",
                    "name": "PostgreSQL",
                    "data": {
                        "host": os.environ.get("DB_HOST", "127.0.0.1"),
                        "port": os.environ.get("DB_PORT", "5432"),
                        "dbname": os.environ.get("DB_NAME")
                        or os.environ.get("DB_DATABASE", "postgres"),
                        "user": os.environ.get("DB_USER", "postgres"),
                        "password": os.environ.get("DB_PASSWORD", ""),
                        "search_path": [resource.schema_name, "public"],
                    },
                    "table": resource.qualified_table_name,
                    "id_field": resource.primary_key,
                    "geom_field": resource.geometry_field,
                }
            ],
        }

    return resources


def sync_pygeoapi_settings():
    try:
        catalog_resources = build_pygeoapi_resources_from_catalog()
    except (OperationalError, ProgrammingError):
        return

    base_resources = {
        key: value
        for key, value in settings.PYGEOAPI_CONFIG.get("resources", {}).items()
        if not value.get("metadata", {}).get("catalog_managed", False)
    }
    for value in catalog_resources.values():
        value.setdefault("metadata", {})["catalog_managed"] = True

    base_resources.update(catalog_resources)
    settings.PYGEOAPI_CONFIG["resources"] = base_resources
    settings.OPENAPI_DOCUMENT = get_oas(settings.PYGEOAPI_CONFIG)
