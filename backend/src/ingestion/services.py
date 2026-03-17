import hashlib
import io
import json
import mimetypes
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import geopandas as gpd
import pandas as pd
import yaml
from geoalchemy2 import Geometry
from geopandas.io.sql import (
    _convert_linearring_to_linestring,
    _convert_to_ewkb,
    _get_geometry_type,
    _get_srid_from_crs,
    _psql_insert_copy,
)

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.text import slugify
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from catalog.file_formats import (
    API_SPEC_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SPATIAL_EXTENSIONS,
    TABULAR_EXTENSIONS,
    is_allowed_upload_extension,
    is_api_spec_extension,
)
from catalog.models import Resource, ResourceAPI, ResourceTable


IDENTIFIER_MAX_LENGTH = 63
NON_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")
LATITUDE_COLUMN_NAMES = {"lat", "latitude", "latitud"}
LONGITUDE_COLUMN_NAMES = {"lon", "lng", "long", "longitude", "longitud"}


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


def _read_document_file_bytes(document):
    if document is None or not getattr(document, "file", None):
        return None

    document_file = document.file
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
    if suffix == ".json":
        file_representation = getattr(resource, "file_representation", None)
        raw_content = _read_document_bytes(file_representation)
        if _json_bytes_look_like_geojson(raw_content):
            return Resource.ResourceKind.SPATIAL
    if suffix == ".csv":
        file_representation = getattr(resource, "file_representation", None)
        if file_representation is not None and _csv_has_coordinate_columns(file_representation):
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


def _reserve_internal_column_names(dataframe, column_mapping, reserved_names):
    normalized_dataframe = dataframe.copy()
    updated_mapping = dict(column_mapping)
    used_names = set(normalized_dataframe.columns)
    renamed_columns = {}

    for column_name in list(normalized_dataframe.columns):
        if column_name not in reserved_names:
            continue

        used_names.discard(column_name)
        replacement = _normalize_identifier(f"source_{column_name}", 1, used_names)
        renamed_columns[column_name] = replacement

        for source_name, normalized_name in updated_mapping.items():
            if normalized_name == column_name:
                updated_mapping[source_name] = replacement

    if renamed_columns:
        normalized_dataframe = normalized_dataframe.rename(columns=renamed_columns)

    return normalized_dataframe, updated_mapping


def _detect_csv_coordinate_columns(dataframe):
    latitude_column = next(
        (column_name for column_name in dataframe.columns if column_name in LATITUDE_COLUMN_NAMES),
        None,
    )
    longitude_column = next(
        (column_name for column_name in dataframe.columns if column_name in LONGITUDE_COLUMN_NAMES),
        None,
    )
    if latitude_column and longitude_column:
        return latitude_column, longitude_column
    return None, None


def _csv_has_coordinate_columns(file_representation):
    dataframe, _column_mapping = _load_csv_dataframe(file_representation)
    latitude_column, longitude_column = _detect_csv_coordinate_columns(dataframe)
    return bool(latitude_column and longitude_column)


def _build_ingested_table_name(resource):
    return _build_layer_table_name(resource)


def _build_layer_table_name(resource, layer_name=None):
    base_name = slugify(
        "_".join(
            part
            for part in [resource.dataset.slug, resource.slug, layer_name]
            if part
        ),
        allow_unicode=False,
    ).replace("-", "_") or f"resource_{resource.pk}"
    digest = hashlib.sha1(
        f"{resource.dataset_id}:{resource.slug}:{layer_name or ''}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    prefix = base_name[: IDENTIFIER_MAX_LENGTH - len(digest) - 1]
    return f"{prefix}_{digest}"


def _build_spatial_index_name(table_name, geometry_field):
    base_name = slugify(
        f"{table_name}_{geometry_field}_gist",
        allow_unicode=False,
    ).replace("-", "_") or "spatial_index"
    digest = hashlib.sha1(
        f"{table_name}:{geometry_field}:gist".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    prefix = base_name[: IDENTIFIER_MAX_LENGTH - len(digest) - 1]
    return f"{prefix}_{digest}"


def _write_geodataframe_to_postgis(db_connection, schema_name, table_name, geodataframe, geometry_field):
    geometry_type, has_curve = _get_geometry_type(geodataframe)
    srid = _get_srid_from_crs(geodataframe)
    prepared_geodataframe = geodataframe.copy()

    if has_curve:
        prepared_geodataframe = _convert_linearring_to_linestring(
            prepared_geodataframe,
            geometry_field,
        )

    dataframe = _convert_to_ewkb(prepared_geodataframe, geometry_field, srid)
    dataframe.to_sql(
        name=table_name,
        con=db_connection,
        schema=schema_name,
        if_exists="replace",
        index=True,
        index_label="id",
        dtype={
            geometry_field: Geometry(
                geometry_type=geometry_type,
                srid=srid,
                spatial_index=False,
            )
        },
        method=_psql_insert_copy,
    )


def _load_csv_dataframe(file_representation):
    raw_content = _read_document_bytes(file_representation)
    return _load_csv_dataframe_from_bytes(raw_content)


def _load_csv_dataframe_from_bytes(raw_content):
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

    dataframe, column_mapping = _normalize_dataframe_columns(dataframe)
    dataframe, column_mapping = _reserve_internal_column_names(
        dataframe,
        column_mapping,
        {"id"},
    )
    dataframe = dataframe.reset_index(drop=True)
    dataframe.index = pd.RangeIndex(start=1, stop=len(dataframe) + 1, step=1, name="id")
    return dataframe, column_mapping


def _replace_tabular_table(schema_name, table_name, dataframe):
    quoted_schema = connection.ops.quote_name(schema_name)
    quoted_table = connection.ops.quote_name(table_name)
    engine = create_engine(_sqlalchemy_database_url(), future=True)

    try:
        with engine.begin() as db_connection:
            db_connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}"))
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
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            [resource_table.schema_name, resource_table.table_name],
        )
        column_names = [row[0] for row in cursor.fetchall()]

        if resource_table.geometry_field and resource_table.geometry_field in column_names:
            select_columns = []
            for column_name in column_names:
                quoted_column = connection.ops.quote_name(column_name)
                if column_name == resource_table.geometry_field:
                    select_columns.append(
                        f"ST_AsGeoJSON({quoted_column})::jsonb AS {quoted_column}"
                    )
                else:
                    select_columns.append(quoted_column)
            select_clause = ", ".join(select_columns)
        else:
            select_clause = "*"

        cursor.execute(
            f"SELECT {select_clause} FROM {qualified_table} ORDER BY {connection.ops.quote_name(resource_table.primary_key)} ASC LIMIT %s OFFSET %s",
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

    _delete_stale_resource_tables(resource, {table_name})


def _delete_stale_resource_tables(resource, keep_table_names):
    for resource_table in resource.tables.exclude(table_name__in=keep_table_names):
        resource_table.delete()


def _sync_spatial_resource_table(
    resource,
    schema_name,
    table_name,
    row_count,
    geometry_field,
    srid,
    bbox,
):
    existing = resource.tables.filter(is_primary=True).order_by("id").first()
    expected_values = {
        "layer_name": resource.title,
        "schema_name": schema_name,
        "table_name": table_name,
        "primary_key": "id",
        "geometry_field": geometry_field,
        "srid": srid,
        "row_count": row_count,
        "bbox": bbox,
        "ogc_api_enabled": bool(geometry_field),
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

    _delete_stale_resource_tables(resource, {table_name})


def _sync_spatial_resource_tables(resource, schema_name, table_definitions):
    existing_tables = {
        resource_table.table_name: resource_table
        for resource_table in resource.tables.order_by("id")
    }
    desired_table_names = {table_definition["table_name"] for table_definition in table_definitions}
    new_resource_tables = []

    for table_definition in table_definitions:
        table_name = table_definition["table_name"]
        existing = existing_tables.get(table_name)
        expected_values = {
            "layer_name": table_definition["layer_name"],
            "schema_name": schema_name,
            "table_name": table_name,
            "primary_key": "id",
            "geometry_field": table_definition["geometry_field"],
            "srid": table_definition["srid"],
            "row_count": table_definition["row_count"],
            "bbox": table_definition["bbox"],
            "ogc_api_enabled": bool(table_definition["geometry_field"]),
            "is_primary": table_definition["is_primary"],
        }

        if existing is None:
            new_resource_tables.append(ResourceTable(resource=resource, **expected_values))
            continue

        updates = {
            field_name: value
            for field_name, value in expected_values.items()
            if getattr(existing, field_name) != value
        }
        if updates:
            ResourceTable.objects.filter(pk=existing.pk).update(**updates)

    if new_resource_tables:
        ResourceTable.objects.bulk_create(new_resource_tables)

    _delete_stale_resource_tables(resource, desired_table_names)


def _csv_bytes_have_coordinate_columns(raw_content):
    dataframe, _column_mapping = _load_csv_dataframe_from_bytes(raw_content)
    latitude_column, longitude_column = _detect_csv_coordinate_columns(dataframe)
    return bool(latitude_column and longitude_column)


def _json_bytes_look_like_geojson(raw_content):
    if not raw_content:
        return False

    try:
        payload = json.loads(raw_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False

    if not isinstance(payload, dict):
        return False

    geojson_type = str(payload.get("type", "")).strip()
    if geojson_type == "FeatureCollection" and isinstance(payload.get("features"), list):
        return True
    if geojson_type == "Feature" and isinstance(payload.get("geometry"), dict):
        return True
    if geojson_type in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }:
        return True

    return False


def suggest_resource_kind_from_source(filename, current_kind=None, raw_content=None):
    suffix = Path(filename or "").suffix.lower()
    current_kind = current_kind or Resource.ResourceKind.DOCUMENT

    if suffix in SPATIAL_EXTENSIONS:
        return Resource.ResourceKind.SPATIAL
    if suffix == ".json":
        if _json_bytes_look_like_geojson(raw_content):
            return Resource.ResourceKind.SPATIAL
        return Resource.ResourceKind.API if current_kind == Resource.ResourceKind.API else current_kind
    if suffix == ".csv":
        try:
            if raw_content is not None and _csv_bytes_have_coordinate_columns(raw_content):
                return Resource.ResourceKind.SPATIAL
        except ValueError:
            pass
        return Resource.ResourceKind.TABULAR
    if suffix in {".tsv", ".parquet"}:
        return Resource.ResourceKind.TABULAR
    if suffix in IMAGE_EXTENSIONS:
        return Resource.ResourceKind.IMAGE
    if suffix in DOCUMENT_EXTENSIONS:
        return Resource.ResourceKind.DOCUMENT
    if suffix in {".yaml", ".yml"}:
        return Resource.ResourceKind.API if current_kind == Resource.ResourceKind.API else current_kind
    return current_kind


def suggest_resource_kind_from_document(document, current_kind=None):
    filename = getattr(document, "filename", "") or getattr(getattr(document, "file", None), "name", "")
    raw_content = None
    if Path(filename).suffix.lower() in {".csv", ".json", ".geojson"}:
        raw_content = _read_document_file_bytes(document)
    return suggest_resource_kind_from_source(
        filename,
        current_kind=current_kind,
        raw_content=raw_content,
    )


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


def _load_spatial_csv_geodataframe(file_representation):
    dataframe, column_mapping = _load_csv_dataframe(file_representation)
    dataframe, column_mapping = _reserve_internal_column_names(
        dataframe,
        column_mapping,
        {"geometry"},
    )
    latitude_column, longitude_column = _detect_csv_coordinate_columns(dataframe)
    if not latitude_column or not longitude_column:
        raise ValueError("CSV spatial ingestion requires latitude and longitude columns.")

    latitude_values = pd.to_numeric(dataframe[latitude_column], errors="coerce")
    longitude_values = pd.to_numeric(dataframe[longitude_column], errors="coerce")
    valid_rows = latitude_values.notna() & longitude_values.notna()
    if not valid_rows.any():
        raise ValueError("CSV spatial ingestion requires numeric latitude and longitude values.")

    if not latitude_values[valid_rows].between(-90, 90).all():
        raise ValueError("Latitude values must be between -90 and 90.")
    if not longitude_values[valid_rows].between(-180, 180).all():
        raise ValueError("Longitude values must be between -180 and 180.")

    geodataframe = gpd.GeoDataFrame(
        dataframe.copy(),
        geometry=gpd.points_from_xy(longitude_values, latitude_values),
        crs="EPSG:4326",
    )
    geometry_field = "geometry"
    return geodataframe, column_mapping, geometry_field, latitude_column, longitude_column


def _ingest_spatial_csv_resource(resource, file_representation, metadata):
    schema_name = ensure_resource_data_schema()
    geodataframe, column_mapping, geometry_field, latitude_column, longitude_column = (
        _load_spatial_csv_geodataframe(file_representation)
    )
    table_name = _build_ingested_table_name(resource)
    _replace_spatial_table(schema_name, table_name, geodataframe, geometry_field)

    bbox = []
    if not geodataframe.empty:
        total_bounds = geodataframe.total_bounds.tolist()
        if len(total_bounds) == 4:
            bbox = [float(value) for value in total_bounds]

    srid = 4326
    _sync_spatial_resource_table(
        resource,
        schema_name,
        table_name,
        len(geodataframe.index),
        geometry_field,
        srid,
        bbox,
    )

    metadata["target_schema"] = schema_name
    metadata["target_table"] = table_name
    metadata["ingested_columns"] = list(geodataframe.columns)
    metadata["source_column_map"] = column_mapping
    metadata["geometry_field"] = geometry_field
    metadata["row_count"] = len(geodataframe.index)
    metadata["bbox"] = bbox
    metadata["srid"] = srid
    metadata["latitude_column"] = latitude_column
    metadata["longitude_column"] = longitude_column

    return {
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": f"Spatial CSV ingested into {schema_name}.{table_name}.",
    }


def _load_geojson_geodataframe(file_representation):
    raw_content = _read_document_bytes(file_representation)
    if raw_content is None:
        raise ValueError("GeoJSON ingestion requires a readable source document.")

    geodataframe = _read_vector_file_from_bytes(raw_content, ".geojson")
    return _normalize_spatial_geodataframe(
        geodataframe,
        empty_message="GeoJSON file does not contain features.",
        missing_geometry_message="GeoJSON file must include a geometry column.",
    )


def _read_vector_file_from_bytes(raw_content, suffix, layer_name=None):
    with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
        temp_file.write(raw_content)
        temp_file.flush()
        read_kwargs = {}
        if layer_name is not None:
            read_kwargs["layer"] = layer_name
        return gpd.read_file(temp_file.name, **read_kwargs)


def _sqlite_quote_identifier(identifier):
    return f'"{str(identifier).replace("\"", "\"\"")}"'


def _normalize_tabular_dataframe(dataframe, *, empty_message):
    if dataframe.empty and len(dataframe.columns) == 0:
        raise ValueError(empty_message)

    normalized_dataframe, column_mapping = _normalize_dataframe_columns(dataframe)
    normalized_dataframe, column_mapping = _reserve_internal_column_names(
        normalized_dataframe,
        column_mapping,
        {"id"},
    )
    normalized_dataframe = normalized_dataframe.reset_index(drop=True)
    normalized_dataframe.index = pd.RangeIndex(
        start=1,
        stop=len(normalized_dataframe) + 1,
        step=1,
        name="id",
    )
    return normalized_dataframe, column_mapping


def _normalize_spatial_geodataframe(
    geodataframe,
    *,
    empty_message,
    missing_geometry_message,
):
    if geodataframe.empty and len(geodataframe.columns) == 0:
        raise ValueError(empty_message)

    if geodataframe.geometry is None or geodataframe.geometry.name not in geodataframe.columns:
        raise ValueError(missing_geometry_message)

    if geodataframe.crs is None:
        geodataframe = geodataframe.set_crs(epsg=4326)
    elif geodataframe.crs.to_epsg() != 4326:
        geodataframe = geodataframe.to_crs(epsg=4326)

    geometry_column = geodataframe.geometry.name
    used_names = set()
    normalized_columns = [
        _normalize_identifier(column_name, index, used_names)
        for index, column_name in enumerate(geodataframe.columns, start=1)
    ]
    column_mapping = dict(zip(geodataframe.columns, normalized_columns, strict=False))

    normalized_geodataframe = geodataframe.copy()
    normalized_geodataframe.columns = normalized_columns
    normalized_geodataframe, column_mapping = _reserve_internal_column_names(
        normalized_geodataframe,
        column_mapping,
        {"id"},
    )
    normalized_geometry_column = column_mapping[geometry_column]
    normalized_geodataframe = normalized_geodataframe.set_geometry(normalized_geometry_column)
    normalized_geodataframe = normalized_geodataframe.reset_index(drop=True)
    normalized_geodataframe.index = pd.RangeIndex(
        start=1,
        stop=len(normalized_geodataframe) + 1,
        step=1,
        name="id",
    )
    return normalized_geodataframe, column_mapping, normalized_geometry_column


def _load_geopackage_layers(file_representation):
    raw_content = _read_document_bytes(file_representation)
    if raw_content is None:
        raise ValueError("GeoPackage ingestion requires a readable source document.")

    with tempfile.NamedTemporaryFile(suffix=".gpkg") as temp_file:
        temp_file.write(raw_content)
        temp_file.flush()

        with sqlite3.connect(temp_file.name) as sqlite_connection:
            cursor = sqlite_connection.cursor()
            cursor.execute(
                """
                SELECT
                    c.table_name,
                    COALESCE(NULLIF(c.identifier, ''), c.table_name),
                    c.data_type
                FROM gpkg_contents AS c
                WHERE c.data_type IN ('features', 'attributes')
                ORDER BY
                    CASE c.data_type
                        WHEN 'features' THEN 0
                        ELSE 1
                    END,
                    c.table_name
                """
            )
            layer_rows = cursor.fetchall()

        if not layer_rows:
            raise ValueError("GeoPackage file does not contain ingestible layers.")

        layers = []
        for source_layer_name, display_layer_name, data_type in layer_rows:
            if data_type == "features":
                geodataframe = gpd.read_file(temp_file.name, layer=source_layer_name)
                normalized_geodataframe, column_mapping, geometry_field = _normalize_spatial_geodataframe(
                    geodataframe,
                    empty_message=f"GeoPackage layer '{display_layer_name}' does not contain features.",
                    missing_geometry_message=(
                        f"GeoPackage layer '{display_layer_name}' must include a geometry column."
                    ),
                )
                layers.append(
                    {
                        "source_layer_name": source_layer_name,
                        "display_layer_name": display_layer_name,
                        "data_type": data_type,
                        "dataframe": normalized_geodataframe,
                        "column_mapping": column_mapping,
                        "geometry_field": geometry_field,
                    }
                )
                continue

            dataframe = pd.read_sql_query(
                f"SELECT * FROM {_sqlite_quote_identifier(source_layer_name)}",
                sqlite_connection,
            )
            normalized_dataframe, column_mapping = _normalize_tabular_dataframe(
                dataframe,
                empty_message=f"GeoPackage table '{display_layer_name}' does not contain columns.",
            )
            layers.append(
                {
                    "source_layer_name": source_layer_name,
                    "display_layer_name": display_layer_name,
                    "data_type": data_type,
                    "dataframe": normalized_dataframe,
                    "column_mapping": column_mapping,
                    "geometry_field": "",
                }
            )

    return layers


def _replace_spatial_table(schema_name, table_name, geodataframe, geometry_field):
    quoted_schema = connection.ops.quote_name(schema_name)
    quoted_table = connection.ops.quote_name(table_name)
    quoted_index_name = connection.ops.quote_name(
        _build_spatial_index_name(table_name, geometry_field)
    )
    engine = create_engine(_sqlalchemy_database_url(), future=True)

    try:
        with engine.begin() as db_connection:
            db_connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}"))
            _write_geodataframe_to_postgis(
                db_connection,
                schema_name,
                table_name,
                geodataframe,
                geometry_field,
            )
            db_connection.execute(
                text(f"ALTER TABLE {quoted_schema}.{quoted_table} ADD PRIMARY KEY (id)")
            )
            db_connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {quoted_index_name} "
                    f"ON {quoted_schema}.{quoted_table} USING GIST ({connection.ops.quote_name(geometry_field)})"
                )
            )
    finally:
        engine.dispose()


def _ingest_geojson_resource(resource, file_representation, metadata):
    schema_name = ensure_resource_data_schema()
    geodataframe, column_mapping, geometry_field = _load_geojson_geodataframe(file_representation)
    table_name = _build_ingested_table_name(resource)
    _replace_spatial_table(schema_name, table_name, geodataframe, geometry_field)

    bbox = []
    if not geodataframe.empty:
        total_bounds = geodataframe.total_bounds.tolist()
        if len(total_bounds) == 4:
            bbox = [float(value) for value in total_bounds]

    srid = geodataframe.crs.to_epsg() if geodataframe.crs is not None else 4326
    if srid is None:
        srid = 4326

    _sync_spatial_resource_table(
        resource,
        schema_name,
        table_name,
        len(geodataframe.index),
        geometry_field,
        srid,
        bbox,
    )

    metadata["target_schema"] = schema_name
    metadata["target_table"] = table_name
    metadata["ingested_columns"] = list(geodataframe.columns)
    metadata["source_column_map"] = column_mapping
    metadata["geometry_field"] = geometry_field
    metadata["row_count"] = len(geodataframe.index)
    metadata["bbox"] = bbox
    metadata["srid"] = srid

    return {
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": f"GeoJSON ingested into {schema_name}.{table_name}.",
    }


def _ingest_geopackage_resource(resource, file_representation, metadata):
    schema_name = ensure_resource_data_schema()
    layers = _load_geopackage_layers(file_representation)
    ingested_layers = []

    for index, layer in enumerate(layers):
        dataframe = layer["dataframe"]
        geometry_field = layer["geometry_field"]
        table_name = _build_layer_table_name(resource, layer["source_layer_name"])
        if geometry_field:
            _replace_spatial_table(schema_name, table_name, dataframe, geometry_field)
        else:
            _replace_tabular_table(schema_name, table_name, dataframe)

        bbox = []
        if geometry_field and not dataframe.empty:
            total_bounds = dataframe.total_bounds.tolist()
            if len(total_bounds) == 4:
                bbox = [float(value) for value in total_bounds]

        srid = None
        if geometry_field:
            srid = dataframe.crs.to_epsg() if dataframe.crs is not None else 4326
            if srid is None:
                srid = 4326

        ingested_layers.append(
            {
                "layer_name": layer["display_layer_name"],
                "source_layer_name": layer["source_layer_name"],
                "data_type": layer["data_type"],
                "table_name": table_name,
                "geometry_field": geometry_field,
                "srid": srid,
                "bbox": bbox,
                "row_count": len(dataframe.index),
                "is_primary": index == 0,
                "ingested_columns": list(dataframe.columns),
                "source_column_map": layer["column_mapping"],
            }
        )

    _sync_spatial_resource_tables(resource, schema_name, ingested_layers)

    primary_layer = ingested_layers[0]
    metadata["target_schema"] = schema_name
    metadata["target_table"] = primary_layer["table_name"]
    metadata["target_tables"] = [layer["table_name"] for layer in ingested_layers]
    metadata["target_layers"] = [
        {
            "source_layer_name": layer["source_layer_name"],
            "display_layer_name": layer["layer_name"],
            "data_type": layer["data_type"],
            "target_table": layer["table_name"],
            "geometry_field": layer["geometry_field"],
            "srid": layer["srid"],
            "bbox": layer["bbox"],
            "row_count": layer["row_count"],
            "ingested_columns": layer["ingested_columns"],
            "source_column_map": layer["source_column_map"],
            "is_primary": layer["is_primary"],
        }
        for layer in ingested_layers
    ]
    metadata["ingested_columns"] = primary_layer["ingested_columns"]
    metadata["source_column_map"] = primary_layer["source_column_map"]
    metadata["geometry_field"] = primary_layer["geometry_field"]
    metadata["row_count"] = sum(layer["row_count"] for layer in ingested_layers)
    metadata["bbox"] = primary_layer["bbox"]
    metadata["srid"] = primary_layer["srid"]
    metadata["layer_count"] = len(ingested_layers)

    return {
        "processing_status": Resource.ProcessingStatus.READY,
        "processing_message": (
            f"GeoPackage ingested into {schema_name} with {len(ingested_layers)} layer(s)."
        ),
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
            if _document_suffix(resource) == ".csv" and file_representation is not None:
                processing_overrides.update(
                    _ingest_spatial_csv_resource(resource, file_representation, metadata)
                )
            elif (
                _document_suffix(resource) in {".geojson", ".json"}
                and file_representation is not None
            ):
                processing_overrides.update(
                    _ingest_geojson_resource(resource, file_representation, metadata)
                )
            elif _document_suffix(resource) == ".gpkg" and file_representation is not None:
                processing_overrides.update(
                    _ingest_geopackage_resource(resource, file_representation, metadata)
                )
            else:
                processing_overrides["processing_message"] = (
                    "Spatial resource detected. Synchronous ingestion is currently implemented for CSV with lat/lon, GeoJSON, and GeoPackage files only."
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