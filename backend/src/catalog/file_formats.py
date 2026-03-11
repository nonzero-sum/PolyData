from pathlib import Path

from django.core.exceptions import ValidationError


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".svg",
}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".zip",
}

API_SPEC_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
}

TABULAR_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".parquet",
}

SPATIAL_EXTENSIONS = {
    ".geojson",
    ".gpkg",
}

ALLOWED_UPLOAD_EXTENSIONS = (
    IMAGE_EXTENSIONS
    | DOCUMENT_EXTENSIONS
    | API_SPEC_EXTENSIONS
    | TABULAR_EXTENSIONS
    | SPATIAL_EXTENSIONS
)


def get_file_extension(filename):
    return Path(filename or "").suffix.lower()


def is_allowed_upload_extension(filename):
    return get_file_extension(filename) in ALLOWED_UPLOAD_EXTENSIONS


def is_api_spec_extension(filename):
    return get_file_extension(filename) in API_SPEC_EXTENSIONS


def allowed_upload_extensions_display():
    return ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))


def allowed_upload_extensions_accept():
    return ",".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))


def validate_allowed_upload(filename, field_name="file"):
    if is_allowed_upload_extension(filename):
        return

    raise ValidationError(
        {
            field_name: (
                "Only supported formats are allowed. "
                f"Allowed extensions: {allowed_upload_extensions_display()}."
            )
        }
    )