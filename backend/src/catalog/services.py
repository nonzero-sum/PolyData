import hashlib
import io
import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml

from django.conf import settings
from django.db import connection
from django.utils.text import slugify
from django.utils import timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from .file_formats import (
    API_SPEC_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SPATIAL_EXTENSIONS,
    TABULAR_EXTENSIONS,
    is_api_spec_extension,
    is_allowed_upload_extension,
)
from .models import Resource, ResourceAPI, ResourceTable


IDENTIFIER_MAX_LENGTH = 63
NON_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")


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


def _sqlalchemy_database_url():
    database = settings.DATABASES["default"]
    return URL.create(
        drivername="postgresql+psycopg2",
        username=database.get("USER") or None,
        password=database.get("PASSWORD") or None,
        host=database.get("HOST") or None,
        port=int(database["PORT"]) if database.get("PORT") else None,
        database=database.get("NAME") or None,
    )


def _normalize_identifier(value, index, used_names):
    normalized = slugify(str(value or ""), allow_unicode=False).replace("-", "_")
    normalized = NON_IDENTIFIER_CHARS.sub("_", normalized.lower()).strip("_")

    if not normalized:
        normalized = f"column_{index}"
    if normalized[0].isdigit():
        normalized = f"column_{normalized}"

    candidate = normalized[:IDENTIFIER_MAX_LENGTH]
    counter = 2
    while candidate in used_names:
        suffix = f"_{counter}"
        candidate = f"{normalized[: IDENTIFIER_MAX_LENGTH - len(suffix)]}{suffix}"
        counter += 1

    used_names.add(candidate)
    return candidate


def _normalize_dataframe_columns(dataframe):
    used_names = set()
    normalized_columns = [
        _normalize_identifier(column_name, index, used_names)
        for index, column_name in enumerate(dataframe.columns, start=1)
    ]

    normalized_dataframe = dataframe.copy()
    normalized_dataframe.columns = normalized_columns
    return normalized_dataframe, dict(zip(dataframe.columns, normalized_columns, strict=False))


def _build_ingested_table_name(resource):
    base_name = slugify(
        f"{resource.dataset.slug}_{resource.slug}",
        allow_unicode=False,
    ).replace("-", "_") or f"resource_{resource.pk}"
    digest = hashlib.sha1(
        f"{resource.dataset_id}:{resource.slug}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    prefix = base_name[: IDENTIFIER_MAX_LENGTH - len(digest) - 1]
    return f"{prefix}_{digest}"


def _load_csv_dataframe(file_representation):
    raw_content = _read_document_bytes(file_representation)
    if raw_content is None:
        raise ValueError("CSV ingestion requires a readable source document.")

    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            dataframe = pd.read_csv(io.BytesIO(raw_content), encoding=encoding)
            break
        except UnicodeDecodeError as error:
            last_error = error
    else:
        raise ValueError("CSV file could not be decoded.") from last_error

    if dataframe.empty and len(dataframe.columns) == 0:
        raise ValueError("CSV file must contain a header row.")

    dataframe = dataframe.reset_index(drop=True)
    dataframe.index = pd.RangeIndex(start=1, stop=len(dataframe) + 1, step=1, name="id")
    return _normalize_dataframe_columns(dataframe)


def _replace_tabular_table(schema_name, table_name, dataframe):
    quoted_schema = connection.ops.quote_name(schema_name)
    quoted_table = connection.ops.quote_name(table_name)
    engine = create_engine(_sqlalchemy_database_url(), future=True)

    try:
        with engine.begin() as db_connection:
            dataframe.to_sql(
                name=table_name,
                con=db_connection,
                schema=schema_name,
                if_exists="replace",
                index=True,
                index_label="id",
                method="multi",
            )
            db_connection.execute(
                text(f"ALTER TABLE {quoted_schema}.{quoted_table} ADD PRIMARY KEY (id)")
            )
    finally:
        engine.dispose()


def _drop_table_if_needed(schema_name, table_name):
    if not schema_name or not table_name:
        return

    quoted_schema = connection.ops.quote_name(schema_name)
    quoted_table = connection.ops.quote_name(table_name)
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {quoted_schema}.{quoted_table} CASCADE")


def drop_resource_table_storage(resource_table):
    managed_schema = (settings.RESOURCE_DATA_SCHEMA or "resource_data").strip() or "resource_data"
    if resource_table.schema_name != managed_schema:
        return

    _drop_table_if_needed(resource_table.schema_name, resource_table.table_name)


def get_primary_resource_table(resource):
    primary_table = resource.tables.filter(is_primary=True).order_by("id").first()
    if primary_table is not None:
        return primary_table
    return resource.tables.order_by("id").first()


def fetch_resource_table_rows(resource_table, page=1, page_size=10):
    page = max(int(page), 1)
    page_size = max(min(int(page_size), 100), 1)
    offset = (page - 1) * page_size

    quoted_schema = connection.ops.quote_name(resource_table.schema_name)
    quoted_table = connection.ops.quote_name(resource_table.table_name)
    qualified_table = f"{quoted_schema}.{quoted_table}"

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {qualified_table}")
        total_count = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT * FROM {qualified_table} ORDER BY {connection.ops.quote_name(resource_table.primary_key)} ASC LIMIT %s OFFSET %s",
            [page_size, offset],
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    return {
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "results": rows,
    }


def _sync_tabular_resource_table(resource, schema_name, table_name, row_count):
    existing = resource.tables.filter(is_primary=True).order_by("id").first()
    expected_values = {
        "layer_name": resource.title,
        "schema_name": schema_name,
        "table_name": table_name,
        "primary_key": "id",
        "geometry_field": "",
        "srid": None,
        "row_count": row_count,
        "bbox": [],
        "ogc_api_enabled": False,
        "is_primary": True,
    }

    if existing is None:
        ResourceTable.objects.bulk_create([ResourceTable(resource=resource, **expected_values)])
        return

    previous_location = (existing.schema_name, existing.table_name)
    updates = {
        field_name: value
        for field_name, value in expected_values.items()
        if getattr(existing, field_name) != value
    }
    if updates:
        ResourceTable.objects.filter(pk=existing.pk).update(**updates)
        if previous_location != (schema_name, table_name):
            _drop_table_if_needed(*previous_location)


def _ingest_csv_resource(resource, file_representation, metadata):
    schema_name = ensure_resource_data_schema()
    dataframe, column_mapping = _load_csv_dataframe(file_representation)
    table_name = _build_ingested_table_name(resource)
    _replace_tabular_table(schema_name, table_name, dataframe)
    _sync_tabular_resource_table(resource, schema_name, table_name, len(dataframe.index))

    metadata["target_schema"] = schema_name
    metadata["target_table"] = table_name
    metadata["ingested_columns"] = list(dataframe.columns)
    metadata["source_column_map"] = column_mapping
    metadata["row_count"] = len(dataframe.index)

    return {
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": f"CSV ingested into {schema_name}.{table_name}.",
    }


def ensure_resource_data_schema():
    schema_name = (settings.RESOURCE_DATA_SCHEMA or "resource_data").strip() or "resource_data"
    quoted_schema_name = connection.ops.quote_name(schema_name)

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema_name}")

    return schema_name


def process_resource(resource):
    _sync_api_representation_from_spec(resource)
    detected_type = _detect_resource_type(resource)
    metadata = dict(resource.metadata or {})
    metadata.setdefault("detected_kind", detected_type)

    file_representation = getattr(resource, "file_representation", None)
    source_filename = ""
    if file_representation and file_representation.document and file_representation.document.file:
        source_filename = (
            file_representation.original_filename or file_representation.document.file.name
        )
        metadata.setdefault("source_filename", source_filename)
        if detected_type == Resource.ResourceKind.API and is_api_spec_extension(source_filename):
            metadata.setdefault("api_spec_uploaded", True)

    processing_overrides = {
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": "Resource registered successfully.",
    }

    try:
        if detected_type == Resource.ResourceKind.TABULAR:
            metadata.setdefault("ingestion", "postgres")
            metadata.setdefault("target_schema", settings.RESOURCE_DATA_SCHEMA)
            if _document_suffix(resource) == ".csv" and file_representation is not None:
                processing_overrides.update(
                    _ingest_csv_resource(resource, file_representation, metadata)
                )
            else:
                processing_overrides["processing_message"] = (
                    "Tabular resource detected. Synchronous ingestion is currently implemented for CSV files only."
                )
        elif detected_type == Resource.ResourceKind.SPATIAL:
            ensure_resource_data_schema()
            metadata.setdefault("ingestion", "postgis")
            metadata.setdefault("target_schema", settings.RESOURCE_DATA_SCHEMA)
            processing_overrides["processing_message"] = (
                "Spatial ingestion will be implemented next for GeoPackage and GeoJSON."
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
    except Exception as error:
        processing_overrides = {
            "processing_status": Resource.ProcessingStatus.FAILED,
            "processing_message": f"Ingestion failed: {error}",
        }

    updates = {
        "resource_kind": detected_type,
        "storage_kind": _storage_kind_for_resource(resource, detected_type),
        "media_type": _infer_media_type(file_representation, detected_type),
        "metadata": metadata,
        "processed_at": timezone.now(),
        **processing_overrides,
    }

    Resource.objects.filter(pk=resource.pk).update(**updates)
