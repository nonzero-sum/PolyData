from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import escape, format_html, format_html_join
from django.utils.text import slugify
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from taggit.models import TagBase, TaggedItemBase
from wagtail.admin.panels import FieldPanel, HelpPanel, InlinePanel, MultiFieldPanel
from wagtail.documents import get_document_model_string
from wagtail.log_actions import registry as log_action_registry
from wagtail.snippets.models import register_snippet

from .file_formats import validate_allowed_upload
from .metadata_schemas import DUBLIN_CORE_FIELDS, dublin_core_editable_fields


def _generate_unique_slug(model_class, source_value, instance_pk=None, parent_field=None):
    base_slug = slugify(source_value)[:200] or "item"
    slug = base_slug
    counter = 2

    queryset = model_class.objects.all()
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)

    while True:
        lookup = {"slug": slug}
        if parent_field is not None:
            lookup.update(parent_field)
        if not queryset.filter(**lookup).exists():
            return slug
        slug = f"{base_slug[:190]}-{counter}"
        counter += 1


def _display_user(user):
    if user is None:
        return ""

    full_name_getter = getattr(user, "get_full_name", None)
    if callable(full_name_getter):
        full_name = full_name_getter().strip()
        if full_name:
            return full_name

    username_getter = getattr(user, "get_username", None)
    if callable(username_getter):
        username = username_getter()
        if username:
            return str(username)

    return str(user)


def _default_resource_data_schema():
    return getattr(settings, "RESOURCE_DATA_SCHEMA", "resource_data")


class DerivedTablesPanel(HelpPanel):
    class BoundPanel(HelpPanel.BoundPanel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.content = self._build_content()

        def _build_content(self):
            if not getattr(self.instance, "pk", None):
                return "Derived tables will appear here after ingestion."

            tables = list(self.instance.tables.order_by("-is_primary", "layer_name", "table_name"))
            if not tables:
                return "No derived tables generated yet."

            rows = []
            for table in tables:
                primary_label = " (primary)" if table.is_primary else ""
                geometry = table.geometry_field or "none"
                ogc_api = "yes" if table.ogc_api_enabled else "no"
                rows.append(
                    (
                        f"{escape(table.qualified_table_name)}{primary_label}",
                        f"rows: {table.row_count} | geometry: {escape(geometry)} | ogc api: {ogc_api}",
                    )
                )

            return format_html(
                "<ul>{}</ul>",
                format_html_join(
                    "",
                    "<li><strong>{}</strong><br>{}</li>",
                    rows,
                ),
            )


@register_snippet
class Organization(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    email = models.EmailField(blank=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("url"),
        FieldPanel("email"),
    ]

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(Organization, self.title, self.pk)
        super().save(*args, **kwargs)


@register_snippet
class LicenseType(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    code = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    is_open = models.BooleanField(default=False)

    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("code"),
        FieldPanel("description"),
        FieldPanel("url"),
        FieldPanel("is_open"),
    ]

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.code or self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(LicenseType, self.title, self.pk)
        super().save(*args, **kwargs)


@register_snippet
class DatasetTag(TagBase):
    free_tagging = False

    class Meta:
        verbose_name = "dataset tag"
        verbose_name_plural = "dataset tags"
        ordering = ["name"]


class DatasetTaggedItem(TaggedItemBase):
    content_object = ParentalKey(
        "catalog.Dataset",
        on_delete=models.CASCADE,
        related_name="tagged_items",
    )
    tag = models.ForeignKey(
        "catalog.DatasetTag",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class Dataset(ClusterableModel):
    class UpdateFrequency(models.TextChoices):
        AS_NEEDED = "as_needed", "As needed"
        HOURLY = "hourly", "Hourly"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        ANNUALLY = "annually", "Annually"
        UNKNOWN = "unknown", "Unknown"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    license = models.ForeignKey(
        LicenseType,
        on_delete=models.SET_NULL,
        related_name="datasets",
        blank=True,
        null=True,
    )
    update_frequency = models.CharField(
        max_length=32,
        choices=UpdateFrequency.choices,
        default=UpdateFrequency.UNKNOWN,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="datasets",
        blank=True,
        null=True,
    )
    dc_subject = models.TextField(blank=True)
    dc_description = models.TextField(blank=True)
    dc_date = models.TextField(blank=True)
    dc_type = models.TextField(blank=True)
    dc_format = models.TextField(blank=True)
    dc_source = models.TextField(blank=True)
    dc_language = models.TextField(blank=True)
    dc_relation = models.TextField(blank=True)
    dc_coverage = models.TextField(blank=True)
    tags = ClusterTaggableManager(through="catalog.DatasetTaggedItem", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("description"),
        MultiFieldPanel(
            [
                FieldPanel("license"),
                FieldPanel("update_frequency"),
                FieldPanel("organization"),
                FieldPanel("tags"),
                *[FieldPanel(field_name) for field_name, _label in dublin_core_editable_fields()],
            ],
            heading="Metadata",
        ),
        InlinePanel("resources", label="Resource", heading="Resources"),
    ]

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    @property
    def tag_names(self):
        if not self.pk:
            return []
        return list(self.tags.values_list("name", flat=True))

    def dublin_core_defaults(self):
        return {
            "description": self.description,
        }

    def dublin_core_editor_values(self):
        return {
            "subject": self.dc_subject,
            "description": self.dc_description or self.description,
            "date": self.dc_date,
            "type": self.dc_type,
            "format": self.dc_format,
            "source": self.dc_source,
            "language": self.dc_language,
            "relation": self.dc_relation,
            "coverage": self.dc_coverage,
        }

    def _creator_log_entry(self):
        if not self.pk:
            return None
        return (
            log_action_registry.get_logs_for_instance(self)
            .filter(action="wagtail.create")
            .select_related("user")
            .order_by("timestamp", "id")
            .first()
        )

    def creator_display(self, fallback_user=None):
        creator_entry = self._creator_log_entry()
        if creator_entry is not None:
            return creator_entry.user_display_name
        return _display_user(fallback_user)

    def contributor_names(self):
        contributors = []
        seen = set()
        for resource in self.resources.all():
            creator_name = resource.creator_display()
            if not creator_name or creator_name in seen:
                continue
            seen.add(creator_name)
            contributors.append(creator_name)
        return contributors

    def dublin_core_managed_values(self, fallback_user=None):
        return {
            "title": self.title,
            "creator": self.creator_display(fallback_user=fallback_user),
            "publisher": self.organization,
            "contributor": ", ".join(self.contributor_names()),
            "identifier": self.slug,
            "rights": self.license,
        }

    def get_dublin_core(self, fallback_user=None):
        fields = {field_name: "" for field_name in DUBLIN_CORE_FIELDS}
        fields.update(
            {
                field_name: "" if field_value in (None, "") else str(field_value)
                for field_name, field_value in self.dublin_core_editor_values().items()
            }
        )
        fields.update(
            {
                field_name: "" if field_value in (None, "") else str(field_value)
                for field_name, field_value in self.dublin_core_managed_values(
                    fallback_user=fallback_user,
                ).items()
            }
        )
        return {
            "schema": "dublincore",
            "fields": fields,
        }

    def set_dublin_core(self, value, fallback_user=None):
        fields = {}
        if isinstance(value, dict):
            payload_fields = value.get("fields", {})
            if isinstance(payload_fields, dict):
                fields = payload_fields

        self.dc_subject = fields.get("subject", "") or ""
        self.dc_description = fields.get("description", "") or ""
        self.dc_date = fields.get("date", "") or ""
        self.dc_type = fields.get("type", "") or ""
        self.dc_format = fields.get("format", "") or ""
        self.dc_source = fields.get("source", "") or ""
        self.dc_language = fields.get("language", "") or ""
        self.dc_relation = fields.get("relation", "") or ""
        self.dc_coverage = fields.get("coverage", "") or ""

    dublin_core = property(get_dublin_core, set_dublin_core)
    metadata = property(get_dublin_core, set_dublin_core)

    def get_dublin_core_value(self, field_name):
        return self.dublin_core.get("fields", {}).get(field_name, "")

    def set_dublin_core_value(self, field_name, value):
        if field_name in {"title", "creator", "publisher", "contributor", "identifier", "rights"}:
            return
        setattr(self, f"dc_{field_name}", value or "")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(Dataset, self.title, self.pk)
        super().save(*args, **kwargs)


def _build_dublin_core_property(field_name):
    def getter(self):
        return self.get_dublin_core_value(field_name)

    def setter(self, value):
        self.set_dublin_core_value(field_name, value)

    return property(getter, setter)

class Resource(ClusterableModel):
    class ResourceKind(models.TextChoices):
        IMAGE = "image", "Image"
        DOCUMENT = "document", "Document"
        TABULAR = "tabular", "Tabular"
        SPATIAL = "spatial", "Spatial"
        API = "api", "API"

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class StorageKind(models.TextChoices):
        DEFAULT = "default", "Default"
        DEFAULT_POSTGRES = "default_postgres", "Default + Postgres"

    dataset = ParentalKey(Dataset, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    resource_kind = models.CharField(
        max_length=16,
        choices=ResourceKind.choices,
        default=ResourceKind.DOCUMENT,
    )
    storage_kind = models.CharField(
        max_length=16,
        choices=StorageKind.choices,
        default=StorageKind.DEFAULT,
    )
    media_type = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    published = models.BooleanField(default=True)
    processing_status = models.CharField(
        max_length=16,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    processing_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage_kind = self.normalize_storage_kind(self.storage_kind)

    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("resource_kind"),
        FieldPanel("storage_kind"),
        FieldPanel("media_type"),
        FieldPanel("metadata"),
        FieldPanel("published"),
        MultiFieldPanel(
            [
                FieldPanel("processing_status", read_only=True),
                FieldPanel("processing_message", read_only=True),
                FieldPanel("processed_at", read_only=True),
            ],
            heading="Processing",
        ),
        InlinePanel("file_items", label="File", heading="File Source", max_num=1),
        DerivedTablesPanel(heading="Derived Tables"),
        InlinePanel("api_items", label="API", heading="API Source", max_num=1),
    ]

    class Meta:
        ordering = ["dataset__title", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "slug"],
                name="catalog_resource_dataset_slug_unique",
            )
        ]

    def __str__(self):
        return f"{self.dataset.title} / {self.title}"

    @classmethod
    def normalize_storage_kind(cls, value):
        if value in {cls.StorageKind.DEFAULT, cls.StorageKind.DEFAULT_POSTGRES}:
            return value
        if value in {"postgres", "postgis"}:
            return cls.StorageKind.DEFAULT_POSTGRES
        return cls.StorageKind.DEFAULT

    @classmethod
    def supports_postgres_storage(cls, resource_kind):
        return resource_kind in {cls.ResourceKind.TABULAR, cls.ResourceKind.SPATIAL}

    @property
    def is_geospatial(self):
        if self.resource_kind == self.ResourceKind.SPATIAL:
            return True
        return self.tables.exclude(geometry_field="").exists()

    @property
    def is_image(self):
        return self.resource_kind == self.ResourceKind.IMAGE

    @property
    def is_document(self):
        return self.resource_kind in {self.ResourceKind.DOCUMENT, "file"}

    @property
    def file_representation(self):
        return self.file_items.first()

    @property
    def api_representation(self):
        return self.api_items.first()

    def _creator_log_entry(self):
        if not self.pk:
            return None
        return (
            log_action_registry.get_logs_for_instance(self)
            .filter(action="wagtail.create")
            .select_related("user")
            .order_by("timestamp", "id")
            .first()
        )

    def creator_display(self, fallback_user=None):
        stored_creator = (self.metadata or {}).get("created_by_display", "")
        if stored_creator:
            return stored_creator

        creator_entry = self._creator_log_entry()
        if creator_entry is not None:
            return creator_entry.user_display_name

        return _display_user(fallback_user)

    def clean(self):
        super().clean()
        self.storage_kind = self.normalize_storage_kind(self.storage_kind)


    def save(self, *args, **kwargs):
        if self.resource_kind == "file":
            self.resource_kind = self.ResourceKind.DOCUMENT
        self.storage_kind = self.normalize_storage_kind(self.storage_kind)
        if not self.supports_postgres_storage(self.resource_kind):
            self.storage_kind = self.StorageKind.DEFAULT
        if not self.slug:
            self.slug = _generate_unique_slug(
                Resource,
                self.title,
                self.pk,
                parent_field={"dataset": self.dataset},
            )
        super().save(*args, **kwargs)

class ResourceFile(models.Model):
    resource = ParentalKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="file_items",
    )
    document = models.ForeignKey(
        get_document_model_string(),
        on_delete=models.PROTECT,
        related_name="catalog_resource_files",
        blank=True,
        null=True,
    )
    checksum = models.CharField(max_length=128, blank=True)

    panels = [
        FieldPanel("document"),
        FieldPanel("checksum"),
    ]

    class Meta:
        ordering = ["resource__title"]

    def __str__(self):
        return self.original_filename or self.resource.title

    @property
    def original_filename(self):
        if self.document and self.document.file:
            return self.document.filename
        return ""

    @property
    def size(self):
        if self.document and self.document.file:
            return self.document.file.size or 0
        return 0

    def clean(self):
        super().clean()
        if not self.document:
            return

        filename = self.document.filename or getattr(self.document.file, "name", "")
        validate_allowed_upload(filename, field_name="document")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ResourceTable(models.Model):
    resource = ParentalKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="tables",
    )
    layer_name = models.CharField(max_length=255, blank=True)
    schema_name = models.CharField(max_length=128, default=_default_resource_data_schema)
    table_name = models.CharField(max_length=255)
    primary_key = models.CharField(max_length=128, default="id")
    geometry_field = models.CharField(max_length=128, blank=True)
    srid = models.PositiveIntegerField(blank=True, null=True)
    row_count = models.BigIntegerField(default=0)
    bbox = models.JSONField(default=list, blank=True)
    ogc_api_enabled = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)

    panels = [
        FieldPanel("layer_name"),
        FieldPanel("schema_name"),
        FieldPanel("table_name"),
        FieldPanel("primary_key"),
        FieldPanel("geometry_field"),
        FieldPanel("srid"),
        FieldPanel("row_count"),
        FieldPanel("bbox"),
        FieldPanel("ogc_api_enabled"),
        FieldPanel("is_primary"),
    ]

    class Meta:
        ordering = ["resource__title", "layer_name", "table_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "schema_name", "table_name"],
                name="catalog_resource_table_unique",
            )
        ]

    def __str__(self):
        label = self.layer_name or self.table_name
        return f"{self.resource} / {label}"

    def clean(self):
        super().clean()
        if not self.schema_name:
            self.schema_name = _default_resource_data_schema()

    @property
    def qualified_table_name(self):
        return f"{self.schema_name}.{self.table_name}"

    @property
    def is_geospatial(self):
        return bool(self.geometry_field)

    @property
    def collection_name(self):
        layer_slug = slugify(self.layer_name or self.table_name) or "table"
        return f"{self.resource.dataset.slug}-{self.resource.slug}-{layer_slug}"


class ResourceAPI(models.Model):
    class SpecType(models.TextChoices):
        OPENAPI = "openapi", "OpenAPI"
        OGC_API = "ogc_api", "OGC API"
        WMS = "wms", "WMS"
        WFS = "wfs", "WFS"
        OTHER = "other", "Other"

    class AuthType(models.TextChoices):
        NONE = "none", "None"
        API_KEY = "api_key", "API key"
        BEARER = "bearer", "Bearer"
        BASIC = "basic", "Basic"
        OAUTH2 = "oauth2", "OAuth2"

    resource = ParentalKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="api_items",
    )
    base_url = models.URLField()
    spec_type = models.CharField(max_length=32, choices=SpecType.choices, default=SpecType.OPENAPI)
    spec_url = models.URLField(blank=True)
    auth_type = models.CharField(max_length=16, choices=AuthType.choices, default=AuthType.NONE)
    extra_config = models.JSONField(default=dict, blank=True)

    panels = [
        FieldPanel("base_url"),
        FieldPanel("spec_type"),
        FieldPanel("spec_url"),
        FieldPanel("auth_type"),
        FieldPanel("extra_config"),
    ]

    class Meta:
        ordering = ["resource__title"]

    def __str__(self):
        return f"{self.resource} / {self.base_url}"
