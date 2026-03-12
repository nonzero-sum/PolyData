from rest_framework import serializers

from .models import (
    Dataset,
    DatasetTag,
    LicenseType,
    Organization,
    Resource,
    ResourceAPI,
    ResourceFile,
    ResourceTable,
)


class TagNameListField(serializers.Field):
    default_error_messages = {
        "not_a_list": "Expected a list of tag names.",
        "invalid_item": "Each tag must be a non-empty string.",
        "unknown_tags": "Unknown tags: {tags}",
    }

    def to_representation(self, value):
        return list(value.values_list("name", flat=True))

    def to_internal_value(self, data):
        if data in (None, ""):
            return []
        if not isinstance(data, list):
            self.fail("not_a_list")

        normalized_tags = []
        for item in data:
            if not isinstance(item, str):
                self.fail("invalid_item")
            normalized_name = item.strip()
            if not normalized_name:
                self.fail("invalid_item")
            if normalized_name not in normalized_tags:
                normalized_tags.append(normalized_name)

        existing_names = set(
            DatasetTag.objects.filter(name__in=normalized_tags).values_list("name", flat=True)
        )
        unknown_tags = [tag_name for tag_name in normalized_tags if tag_name not in existing_names]
        if unknown_tags:
            self.fail("unknown_tags", tags=", ".join(unknown_tags))

        return normalized_tags


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "title", "slug", "description", "url", "email"]


class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseType
        fields = ["id", "title", "slug", "code", "description", "url", "is_open"]


class ResourceFileSerializer(serializers.ModelSerializer):
    document_id = serializers.IntegerField(source="document.id", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    download_url = serializers.SerializerMethodField()
    original_filename = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True)

    class Meta:
        model = ResourceFile
        fields = [
            "id",
            "document_id",
            "document_title",
            "original_filename",
            "checksum",
            "size",
            "download_url",
        ]

    def get_download_url(self, obj):
        if not obj.document or not obj.document.file:
            return None
        document_url = getattr(obj.document, "url", "") or obj.document.file.url
        request = self.context.get("request")
        if request is None:
            return document_url
        return request.build_absolute_uri(document_url)


class ResourceTableSerializer(serializers.ModelSerializer):
    collection_name = serializers.ReadOnlyField()
    qualified_table_name = serializers.ReadOnlyField()
    table_url = serializers.SerializerMethodField()
    rows_url = serializers.SerializerMethodField()
    ogc_collection_url = serializers.SerializerMethodField()

    class Meta:
        model = ResourceTable
        fields = [
            "id",
            "layer_name",
            "schema_name",
            "table_name",
            "qualified_table_name",
            "primary_key",
            "geometry_field",
            "srid",
            "row_count",
            "bbox",
            "ogc_api_enabled",
            "is_primary",
            "collection_name",
            "table_url",
            "rows_url",
            "ogc_collection_url",
        ]

    def _build_absolute_or_relative_url(self, path):
        request = self.context.get("request")
        if request is None:
            return path
        return request.build_absolute_uri(path)

    def get_table_url(self, obj):
        return self._build_absolute_or_relative_url(
            f"/api/resources/{obj.resource_id}/tables/{obj.pk}/"
        )

    def get_rows_url(self, obj):
        return self._build_absolute_or_relative_url(
            f"/api/resources/{obj.resource_id}/tables/{obj.pk}/rows/"
        )

    def get_ogc_collection_url(self, obj):
        if not obj.ogc_api_enabled or not obj.geometry_field:
            return None
        return self._build_absolute_or_relative_url(
            f"/geoapi/collections/{obj.collection_name}"
        )


class ResourceAPISerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceAPI
        fields = [
            "id",
            "base_url",
            "spec_type",
            "spec_url",
            "auth_type",
            "extra_config",
        ]


class ResourceSerializer(serializers.ModelSerializer):
    api_url = serializers.SerializerMethodField()
    is_geospatial = serializers.ReadOnlyField()
    file_representation = ResourceFileSerializer(read_only=True)
    tables = ResourceTableSerializer(many=True, read_only=True)
    api_representation = ResourceAPISerializer(read_only=True)

    class Meta:
        model = Resource
        fields = [
            "id",
            "dataset",
            "title",
            "slug",
            "description",
            "resource_kind",
            "storage_kind",
            "media_type",
            "is_geospatial",
            "metadata",
            "published",
            "processing_status",
            "processing_message",
            "processed_at",
            "file_representation",
            "tables",
            "api_representation",
            "api_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "slug",
            "is_geospatial",
            "storage_kind",
            "media_type",
            "processing_status",
            "processing_message",
            "processed_at",
            "created_at",
            "updated_at",
        ]

    def get_api_url(self, obj):
        request = self.context.get("request")
        if request is None:
            return f"/api/resources/{obj.pk}/"
        return request.build_absolute_uri(f"/api/resources/{obj.pk}/")


class DatasetSerializer(serializers.ModelSerializer):
    resources = serializers.SerializerMethodField()
    dublin_core = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    tags = TagNameListField(required=False)
    organization = OrganizationSerializer(read_only=True)
    license = LicenseTypeSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        source="organization",
        write_only=True,
        required=False,
        allow_null=True,
    )
    license_id = serializers.PrimaryKeyRelatedField(
        queryset=LicenseType.objects.all(),
        source="license",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Dataset
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "dc_subject",
            "dc_description",
            "dc_date",
            "dc_type",
            "dc_format",
            "dc_source",
            "dc_language",
            "dc_relation",
            "dc_coverage",
            "dublin_core",
            "metadata",
            "license",
            "update_frequency",
            "organization",
            "organization_id",
            "tags",
            "license_id",
            "resources",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get("include_resources", False):
            self.fields.pop("resources", None)

    def get_dublin_core(self, obj):
        return obj.dublin_core

    def get_metadata(self, obj):
        return obj.metadata

    def get_resources(self, obj):
        queryset = obj.resources.all()
        if self.context.get("public_only", False):
            queryset = queryset.filter(published=True)
        return ResourceSerializer(
            queryset,
            many=True,
            context=self.context,
        ).data

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        dataset = super().create(validated_data)
        if tags:
            dataset.tags.set(tags)
        return dataset

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        dataset = super().update(instance, validated_data)
        if tags is not None:
            dataset.tags.set(tags)
        return dataset
