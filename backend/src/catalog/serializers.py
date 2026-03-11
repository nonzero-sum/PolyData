from rest_framework import serializers

from .metadata_schemas import validate_metadata_payload
from .models import (
    Dataset,
    LicenseType,
    Organization,
    Resource,
    ResourceAPI,
    ResourceFile,
    ResourceTable,
)


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
        request = self.context.get("request")
        if request is None:
            return obj.document.file.url
        return request.build_absolute_uri(obj.document.file.url)


class ResourceTableSerializer(serializers.ModelSerializer):
    collection_name = serializers.ReadOnlyField()
    qualified_table_name = serializers.ReadOnlyField()
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
            "ogc_collection_url",
        ]

    def get_ogc_collection_url(self, obj):
        if not obj.ogc_api_enabled or not obj.geometry_field:
            return None
        request = self.context.get("request")
        path = f"/geoapi/collections/{obj.collection_name}"
        if request is None:
            return path
        return request.build_absolute_uri(path)


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
    resources = ResourceSerializer(many=True, read_only=True)
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

    def validate_metadata(self, value):
        validate_metadata_payload(value)
        return value
