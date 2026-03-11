from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.log_actions import registry as log_action_registry
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.documents import get_document_model_string
from wagtail.snippets.models import register_snippet

from .file_formats import validate_allowed_upload
from .metadata_schemas import DUBLIN_CORE_FIELDS, apply_metadata_field_defaults, dublin_core_editable_fields, metadata_editor_initial, validate_metadata_payload


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
    metadata = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
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
            ],
            heading="Metadata",
        ),
        MultiFieldPanel(
            [FieldPanel(field_name) for field_name, _label in dublin_core_editable_fields()],
            heading="Dublin Core",
        ),
        InlinePanel("resources", label="Resource", heading="Resources"),
    ]

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def dublin_core_defaults(self):
        return {
            "description": self.description,
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
        metadata = metadata_editor_initial(self.metadata)
        metadata["schema"] = "dublincore"
        metadata = apply_metadata_field_defaults(metadata, self.dublin_core_defaults())
        metadata["fields"].update(
            {
                field_name: "" if field_value in (None, "") else str(field_value)
                for field_name, field_value in self.dublin_core_managed_values(
                    fallback_user=fallback_user,
                ).items()
            }
        )
        return metadata

    def set_dublin_core(self, value, fallback_user=None):
        payload = metadata_editor_initial(value)
        payload["schema"] = "dublincore"
        payload = apply_metadata_field_defaults(payload, self.dublin_core_defaults())
        payload["fields"].update(
            {
                field_name: "" if field_value in (None, "") else str(field_value)
                for field_name, field_value in self.dublin_core_managed_values(
                    fallback_user=fallback_user,
                ).items()
            }
        )
        self.metadata = payload

    dublin_core = property(get_dublin_core, set_dublin_core)

    def get_dublin_core_value(self, field_name):
        return self.dublin_core.get("fields", {}).get(field_name, "")

    def set_dublin_core_value(self, field_name, value):
        payload = self.dublin_core
        payload.setdefault("fields", {})[field_name] = value or ""
        self.dublin_core = payload

    def clean(self):
        super().clean()
        self.dublin_core = self.metadata
        validate_metadata_payload(self.metadata)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(Dataset, self.title, self.pk)
        self.dublin_core = self.metadata
        super().save(*args, **kwargs)


def _build_dublin_core_property(field_name):
    def getter(self):
        return self.get_dublin_core_value(field_name)

    def setter(self, value):
        self.set_dublin_core_value(field_name, value)

    return property(getter, setter)


for _field_name in DUBLIN_CORE_FIELDS:
    setattr(Dataset, f"dc_{_field_name}", _build_dublin_core_property(_field_name))


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
                FieldPanel("processing_status"),
                FieldPanel("processing_message"),
                FieldPanel("processed_at"),
            ],
            heading="Processing",
        ),
        InlinePanel("file_items", label="File", heading="File Source", max_num=1),
        InlinePanel("tables", label="Table", heading="Derived Tables"),
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

        if (
            self.storage_kind == self.StorageKind.DEFAULT_POSTGRES
            and not self.supports_postgres_storage(self.resource_kind)
        ):
            raise ValidationError(
                {
                    "storage_kind": (
                        "Default + Postgres is only available for tabular or spatial resources."
                    )
                }
            )

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
    schema_name = models.CharField(max_length=128, default="public")
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
