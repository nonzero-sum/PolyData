import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import yaml

from django.utils import timezone

from .file_formats import (
    API_SPEC_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SPATIAL_EXTENSIONS,
    TABULAR_EXTENSIONS,
    is_api_spec_extension,
    is_allowed_upload_extension,
)
from .models import Resource, ResourceAPI


def _document_filename(resource):
    file_representation = getattr(resource, "file_representation", None)
    if file_representation and file_representation.document and file_representation.document.file:
        return file_representation.document.file.name.lower()
    return ""


def _document_suffix(resource):
    return Path(_document_filename(resource)).suffix.lower()


def _read_document_bytes(file_representation):
    if not file_representation or not file_representation.document or not file_representation.document.file:
        return None

    document_file = file_representation.document.file
    document_file.open("rb")
    try:
        return document_file.read()
    finally:
        document_file.close()


def _load_api_spec(file_representation):
    filename = file_representation.original_filename or getattr(file_representation.document.file, "name", "")
    if not is_api_spec_extension(filename):
        return None

    raw_content = _read_document_bytes(file_representation)
    if not raw_content:
        return None

    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".json":
            parsed = json.loads(raw_content.decode("utf-8"))
        elif suffix in {".yaml", ".yml"}:
            parsed = yaml.safe_load(raw_content.decode("utf-8"))
        else:
            return None
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError):
        return None

    return parsed if isinstance(parsed, dict) else None


def _extract_api_base_url(specification):
    servers = specification.get("servers") or []
    if servers:
        first_server = servers[0] or {}
        server_url = first_server.get("url", "").strip()
        if urlparse(server_url).scheme and urlparse(server_url).netloc:
            return server_url

    host = specification.get("host", "").strip()
    if host:
        schemes = specification.get("schemes") or ["https"]
        base_path = specification.get("basePath", "").strip()
        return f"{schemes[0]}://{host}{base_path}"

    return ""


def _detect_api_spec_type(specification):
    if specification.get("openapi") or specification.get("swagger"):
        return ResourceAPI.SpecType.OPENAPI
    return ResourceAPI.SpecType.OTHER


def _detect_api_auth_type(specification):
    security_schemes = specification.get("components", {}).get("securitySchemes", {})
    if not security_schemes:
        security_schemes = specification.get("securityDefinitions", {})

    for scheme in security_schemes.values():
        scheme_type = (scheme or {}).get("type", "")
        if scheme_type == "apiKey":
            return ResourceAPI.AuthType.API_KEY
        if scheme_type == "oauth2":
            return ResourceAPI.AuthType.OAUTH2
        if scheme_type == "http":
            http_scheme = (scheme or {}).get("scheme", "").lower()
            if http_scheme == "bearer":
                return ResourceAPI.AuthType.BEARER
            if http_scheme == "basic":
                return ResourceAPI.AuthType.BASIC

    return ResourceAPI.AuthType.NONE


def _build_api_extra_config(specification):
    info = specification.get("info") or {}
    servers = specification.get("servers") or []
    paths = specification.get("paths") or {}
    return {
        "title": info.get("title", ""),
        "version": info.get("version", ""),
        "description": info.get("description", ""),
        "servers": servers,
        "path_count": len(paths),
        "source": "uploaded_spec",
    }


def _sync_api_representation_from_spec(resource):
    if resource.resource_kind != Resource.ResourceKind.API:
        return False

    file_representation = getattr(resource, "file_representation", None)
    specification = _load_api_spec(file_representation)
    if not specification:
        return False

    base_url = _extract_api_base_url(specification)
    if not base_url:
        return False

    defaults = {
        "base_url": base_url,
        "spec_type": _detect_api_spec_type(specification),
        "auth_type": _detect_api_auth_type(specification),
        "extra_config": _build_api_extra_config(specification),
    }

    existing = resource.api_items.first()
    if existing is None:
        ResourceAPI.objects.create(
            resource=resource,
            spec_url="",
            **defaults,
        )
        return True

    changed = False
    for field_name, value in defaults.items():
        if getattr(existing, field_name) != value:
            setattr(existing, field_name, value)
            changed = True

    if changed:
        existing.save(update_fields=[*defaults.keys()])
    return changed


def _detect_resource_type(resource):
    api_representation = getattr(resource, "api_representation", None)
    if api_representation is not None:
        return Resource.ResourceKind.API

    if resource.resource_kind == Resource.ResourceKind.API:
        suffix = _document_suffix(resource)
        if suffix in API_SPEC_EXTENSIONS:
            return Resource.ResourceKind.API

    suffix = _document_suffix(resource)
    if suffix in SPATIAL_EXTENSIONS:
        return Resource.ResourceKind.SPATIAL
    if suffix in TABULAR_EXTENSIONS:
        return Resource.ResourceKind.TABULAR
    if suffix in IMAGE_EXTENSIONS:
        return Resource.ResourceKind.IMAGE
    if suffix in DOCUMENT_EXTENSIONS:
        return Resource.ResourceKind.DOCUMENT
    if suffix and not is_allowed_upload_extension(f"resource{suffix}"):
        return Resource.ResourceKind.DOCUMENT
    if resource.tables.exists():
        if resource.tables.exclude(geometry_field="").exists():
            return Resource.ResourceKind.SPATIAL
        return Resource.ResourceKind.TABULAR
    if suffix:
        guessed_type, _ = mimetypes.guess_type(f"resource{suffix}")
        if guessed_type:
            if guessed_type.startswith("image/"):
                return Resource.ResourceKind.IMAGE
            if guessed_type in {"application/json", "text/csv"} or guessed_type.startswith("text/"):
                return Resource.ResourceKind.TABULAR
            if guessed_type.startswith("application/") or guessed_type.startswith("text/"):
                return Resource.ResourceKind.DOCUMENT
    return Resource.ResourceKind.DOCUMENT


def _storage_kind_for_resource(resource, detected_type):
    if resource.tables.exists():
        return Resource.StorageKind.DEFAULT_POSTGRES
    return Resource.StorageKind.DEFAULT


def _infer_media_type(file_representation, detected_type):
    if file_representation and file_representation.document and file_representation.document.file:
        filename = file_representation.document.file.name.lower()
        suffix = Path(filename).suffix.lower()
        if suffix == ".geojson":
            return "application/geo+json"
        if suffix == ".gpkg":
            return "application/geopackage+sqlite3"
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type:
            return guessed_type
    if detected_type == Resource.ResourceKind.API:
        return "application/json"
    return "application/octet-stream"


def process_resource(resource):
    _sync_api_representation_from_spec(resource)
    detected_type = _detect_resource_type(resource)
    metadata = dict(resource.metadata or {})
    metadata.setdefault("detected_kind", detected_type)

    file_representation = getattr(resource, "file_representation", None)
    if file_representation and file_representation.document and file_representation.document.file:
        metadata.setdefault(
            "source_filename",
            file_representation.original_filename or file_representation.document.file.name,
        )
        if detected_type == Resource.ResourceKind.API and is_api_spec_extension(
            file_representation.original_filename or file_representation.document.file.name
        ):
            metadata.setdefault("api_spec_uploaded", True)

    updates = {
        "resource_kind": detected_type,
        "storage_kind": _storage_kind_for_resource(resource, detected_type),
        "media_type": _infer_media_type(file_representation, detected_type),
        "metadata": metadata,
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": "Resource registered successfully.",
        "processed_at": timezone.now(),
    }

    if detected_type == Resource.ResourceKind.TABULAR:
        metadata.setdefault("ingestion", "postgres")
    elif detected_type == Resource.ResourceKind.SPATIAL:
        metadata.setdefault("ingestion", "postgis")
        if not resource.tables.exists():
            updates["processing_message"] = (
                "Spatial resource detected. Add one or more ResourceTable rows to publish via OGC API."
            )
        elif (
            file_representation
            and file_representation.document
            and file_representation.document.file.name.lower().endswith(".gpkg")
        ):
            metadata.setdefault(
                "ingestion_note",
                "GeoPackage sources can generate multiple ResourceTable layers.",
            )
    elif detected_type == Resource.ResourceKind.API:
        metadata.setdefault("ingestion", "external")
        metadata.setdefault("preview_kind", "api")
    elif detected_type == Resource.ResourceKind.IMAGE:
        metadata.setdefault("ingestion", "document-library")
        metadata.setdefault("preview_kind", "image")
    elif detected_type == Resource.ResourceKind.DOCUMENT:
        metadata.setdefault("ingestion", "document-library")
        metadata.setdefault("preview_kind", "document")
    else:
        metadata.setdefault("ingestion", "storage")

    Resource.objects.filter(pk=resource.pk).update(**updates)
