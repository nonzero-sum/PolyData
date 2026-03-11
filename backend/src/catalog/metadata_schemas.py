from django.core.exceptions import ValidationError


DUBLIN_CORE_FIELDS = (
    "title",
    "creator",
    "subject",
    "description",
    "publisher",
    "contributor",
    "date",
    "type",
    "format",
    "identifier",
    "source",
    "language",
    "relation",
    "coverage",
    "rights",
)

DUBLIN_CORE_MANAGED_FIELDS = (
    "title",
    "creator",
    "publisher",
    "contributor",
    "identifier",
    "rights",
)

DUBLIN_CORE_FIELD_LABELS = {
    "title": "Title",
    "creator": "Creator",
    "subject": "Subject",
    "description": "Description",
    "publisher": "Publisher",
    "contributor": "Contributor",
    "date": "Date",
    "type": "Type",
    "format": "Format",
    "identifier": "Identifier",
    "source": "Source",
    "language": "Language",
    "relation": "Relation",
    "coverage": "Coverage",
    "rights": "Rights",
}

SUPPORTED_METADATA_SCHEMAS = {
    "dublincore": {
        "label": "Dublin Core",
        "fields": DUBLIN_CORE_FIELDS,
    }
}


def supported_metadata_schemas_display():
    return ", ".join(sorted(SUPPORTED_METADATA_SCHEMAS))


def default_metadata_payload(schema="dublincore"):
    schema_config = SUPPORTED_METADATA_SCHEMAS[schema]
    return {
        "schema": schema,
        "fields": {field_name: "" for field_name in schema_config["fields"]},
    }


def metadata_editor_initial(metadata=None, schema="dublincore"):
    initial = default_metadata_payload(schema=schema)

    if not isinstance(metadata, dict):
        return initial

    merged = dict(metadata)
    merged.setdefault("schema", initial["schema"])

    existing_fields = merged.get("fields")
    if not isinstance(existing_fields, dict):
        existing_fields = {}

    merged["fields"] = {
        **initial["fields"],
        **existing_fields,
    }
    return merged


def apply_metadata_field_defaults(metadata=None, defaults=None, schema="dublincore"):
    merged = metadata_editor_initial(metadata, schema=schema)
    default_fields = defaults or {}

    for field_name, default_value in default_fields.items():
        if field_name not in merged["fields"]:
            continue
        if merged["fields"].get(field_name) not in (None, ""):
            continue
        if default_value in (None, ""):
            continue
        merged["fields"][field_name] = str(default_value)

    return merged


def validate_metadata_payload(metadata, field_name="metadata"):
    if metadata in (None, ""):
        return

    if not isinstance(metadata, dict):
        raise ValidationError({field_name: "Metadata must be a JSON object."})

    schema = metadata.get("schema")
    if schema in (None, ""):
        return

    if schema not in SUPPORTED_METADATA_SCHEMAS:
        raise ValidationError(
            {
                field_name: (
                    "Unsupported metadata schema. "
                    f"Allowed schemas: {supported_metadata_schemas_display()}."
                )
            }
        )

    fields = metadata.get("fields", {})
    if fields in (None, ""):
        fields = {}

    if not isinstance(fields, dict):
        raise ValidationError(
            {field_name: "Metadata fields must be a JSON object when a schema is set."}
        )

    allowed_fields = set(SUPPORTED_METADATA_SCHEMAS[schema]["fields"])
    unknown_fields = sorted(set(fields) - allowed_fields)
    if unknown_fields:
        raise ValidationError(
            {
                field_name: (
                    f"Unsupported fields for schema '{schema}': {', '.join(unknown_fields)}."
                )
            }
        )


def dublin_core_editor_fields(prefix="dc_"):
    return [(f"{prefix}{field_name}", DUBLIN_CORE_FIELD_LABELS[field_name]) for field_name in DUBLIN_CORE_FIELDS]


def dublin_core_editable_fields(prefix="dc_"):
    return [
        (f"{prefix}{field_name}", DUBLIN_CORE_FIELD_LABELS[field_name])
        for field_name in DUBLIN_CORE_FIELDS
        if field_name not in DUBLIN_CORE_MANAGED_FIELDS
    ]