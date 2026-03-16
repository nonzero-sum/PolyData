from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import escape, format_html, format_html_join
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from taggit.models import TagBase, TaggedItemBase
from wagtail.admin.panels import FieldPanel, HelpPanel, InlinePanel, MultiFieldPanel
from wagtail.documents import get_document_model_string
from wagtail.log_actions import registry as log_action_registry
from wagtail.models import DraftStateMixin, RevisionMixin, WorkflowMixin
from wagtail.snippets.models import register_snippet

from paradedb.indexes import BM25Index
from paradedb.queryset import ParadeDBManager

from .file_formats import validate_allowed_upload


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


DATASET_METADATA_FIELD_LABELS = {
    "creation_date": "Creation date",
    "publish_date": "Publish date",
    "update_date": "Update date",
    "source": "Source",
    "type": "Type",
    "coverage": "Coverage",
    "author": "Author",
    "editor": "Editor",
    "other_colabs": "Other collaborators",
    "language": "Language",
}

DATASET_METADATA_FIELD_NAMES = tuple(DATASET_METADATA_FIELD_LABELS)
DATASET_METADATA_EDITABLE_FIELD_NAMES = tuple(
    field_name
    for field_name in DATASET_METADATA_FIELD_NAMES
    if field_name not in {"creation_date", "publish_date", "update_date"}
)


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


class Dataset(WorkflowMixin, DraftStateMixin, RevisionMixin, ClusterableModel):
    # Use Wagtail draft/publish workflow fields so datasets can be managed like pages.
    live = models.BooleanField(verbose_name=_("live"), default=False, editable=False)

    class UpdateFrequency(models.TextChoices):
        AS_NEEDED = "as_needed", "As needed"
        HOURLY = "hourly", "Hourly"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        ANNUALLY = "annually", "Annually"
        UNKNOWN = "unknown", "Unknown"

    # Dates
    creation_date = models.DateField(default=timezone.localdate, editable=False) # 14. DC.Created
    publish_date = models.DateField(blank=True, null=True, editable=False) # 5. DC.Published
    update_date = models.DateField(default=timezone.localdate, editable=False) # 6. DC.Modified

    title = models.CharField(max_length=255) # 1. DC.Title
    slug = models.SlugField(max_length=220, unique=True, blank=True) # 2. DC.Identifier
    description = models.TextField(blank=True) # 3. DC.Description
    source = models.TextField(blank=True) # 4. DC.Source
    type = models.TextField(blank=True) # 5. DC.Type
    coverage = models.TextField(blank=True) # 7. DC.Coverage
    author = models.TextField(blank=True) # 8. DC.Creator
    editor = models.TextField(blank=True) # 9. DC.Publisher
    other_colabs = models.TextField(blank=True) # 10. DC.Contributor
    license = models.ForeignKey(
        LicenseType,
        on_delete=models.SET_NULL,
        related_name="datasets",
        blank=True,
        null=True,
    ) # 11. DC.Rights
    language = models.TextField(blank=True) # 13. DC.Language
    
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
    tags = ClusterTaggableManager(through="catalog.DatasetTaggedItem", blank=True) # 2. DC.Subject

    # ParadeDB full‑text search index (BM25)
    objects = ParadeDBManager()

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
                *[FieldPanel(field_name) for field_name in DATASET_METADATA_EDITABLE_FIELD_NAMES],
            ],
            heading="Metadata",
        ),
        InlinePanel("resources", label="Resource", heading="Resources"),
    ]

    class Meta:
        ordering = ["title"]
        permissions = [
            ("publish_dataset", "Can publish/unpublish dataset"),
            ("manage_dataset_permissions", "Can manage dataset permissions"),
        ]
        indexes = [
            BM25Index(
                fields={
                    "id": {},
                    "title": {"tokenizer": "unicode_words"},
                    "description": {"tokenizer": "unicode_words"},
                    "source": {"tokenizer": "unicode_words"},
                    "type": {"tokenizer": "unicode_words"},
                    "coverage": {"tokenizer": "unicode_words"},
                    "author": {"tokenizer": "unicode_words"},
                    "editor": {"tokenizer": "unicode_words"},
                    "other_colabs": {"tokenizer": "unicode_words"},
                    "language": {"tokenizer": "unicode_words"},
                },
                key_field="id",
                name="dataset_search_idx",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def tag_names(self):
        if not self.pk:
            return []
        return list(self.tags.values_list("name", flat=True))

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

    def save(self, *args, **kwargs):
        today = timezone.localdate()
        if not self.creation_date:
            self.creation_date = today

        # Use Wagtail's `live` flag (draft state) so datasets can be created as drafts.
        # When a dataset becomes live for the first time, set its publish date.
        if self.live and not self.publish_date:
            self.publish_date = today

        self.update_date = today
        if not self.slug:
            self.slug = _generate_unique_slug(Dataset, self.title, self.pk)
        super().save(*args, **kwargs)

class Resource(WorkflowMixin, DraftStateMixin, RevisionMixin, ClusterableModel):
    # Use Wagtail draft/publish workflow fields so resources can be managed like pages.

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
    objects = ParadeDBManager()
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
        # The publish state is managed via the Wagtail action menu (publish/unpublish)
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
        permissions = [
            ("publish_resource", "Can publish/unpublish resource"),
            ("manage_resource_permissions", "Can manage resource permissions"),
        ]
        indexes = [
            BM25Index(
                fields={
                    "id": {},
                    "title": {"tokenizer": "unicode_words"},
                    "description": {"tokenizer": "unicode_words"},
                    "media_type": {"tokenizer": "unicode_words"},
                    "metadata": {},
                },
                key_field="id",
                name="resource_search_idx",
            ),
        ]
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

        # Keep the legacy `published` field in sync with Wagtail's draft state.
        # Publishing/unpublishing is now managed through the Wagtail action menu.
        if hasattr(self, "live"):
            self.published = bool(self.live)

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
