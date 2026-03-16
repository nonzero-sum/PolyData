import json
import re

from django import forms
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.documents import get_document_model
from wagtail.documents.forms import BaseDocumentForm

from .file_formats import allowed_upload_extensions_accept, validate_allowed_upload
from .models import (
    DATASET_METADATA_EDITABLE_FIELD_NAMES,
    DATASET_METADATA_FIELD_LABELS,
    Dataset,
    DatasetTag,
    Resource,
)
from ingestion.services import suggest_resource_kind_from_document


DATASET_METADATA_WIDGET_CONFIG = {
    "source": lambda: forms.Textarea(attrs={"rows": 3}),
    "coverage": lambda: forms.Textarea(attrs={"rows": 3}),
    "author": lambda: forms.Textarea(attrs={"rows": 2}),
    "editor": lambda: forms.Textarea(attrs={"rows": 2}),
    "other_colabs": lambda: forms.Textarea(attrs={"rows": 3}),
}


class CatalogDocumentForm(BaseDocumentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        file_field = self.fields.get("file")
        if file_field is None:
            return

        file_field.widget.attrs["accept"] = allowed_upload_extensions_accept()

        existing_help_text = file_field.help_text or ""
        allowed_help_text = "Allowed formats: " + allowed_upload_extensions_accept()
        if existing_help_text:
            file_field.help_text = f"{existing_help_text} {allowed_help_text}"
        else:
            file_field.help_text = allowed_help_text

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file is None:
            return uploaded_file

        validate_allowed_upload(uploaded_file.name, field_name="file")
        return uploaded_file


class DatasetForm(WagtailAdminModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=DatasetTag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )

    class Meta:
        model = Dataset
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in DATASET_METADATA_EDITABLE_FIELD_NAMES:
            field = self.fields.get(field_name)
            if field is None:
                continue

            field.label = DATASET_METADATA_FIELD_LABELS.get(field_name, field.label)

            widget_factory = DATASET_METADATA_WIDGET_CONFIG.get(field_name)
            if widget_factory is not None:
                field.widget = widget_factory() if callable(widget_factory) else widget_factory()

        tags_field = self.fields.get("tags")
        if tags_field is None:
            return

        tags_field.queryset = DatasetTag.objects.all().order_by("name")
        tags_field.help_text = (
            "Select one or more existing tags. New tags must be created first in Snippets."
        )

        if getattr(self.instance, "pk", None):
            tags_field.initial = self.instance.tags.all()

    def save(self, commit=True):
        selected_tags = self.cleaned_data.get("tags")
        instance = super().save(commit=commit)

        if commit and selected_tags is not None:
            instance.tags.set(selected_tags)

        return instance


class ResourceForm(WagtailAdminModelForm):
    class Meta:
        model = Resource
        fields = "__all__"

    INLINE_DOCUMENT_FIELD_PATTERN = re.compile(r"-(?:\d+-)?document$")
    INLINE_API_BASE_URL_PATTERN = re.compile(r"-(?:\d+-)?base_url$")

    def _selected_document(self):
        if self.is_bound:
            document_model = get_document_model()
            for key, value in self.data.items():
                if not self.INLINE_DOCUMENT_FIELD_PATTERN.search(key):
                    continue

                document_id = (value or "").strip()
                if not document_id:
                    continue

                try:
                    return document_model.objects.get(pk=document_id)
                except (document_model.DoesNotExist, ValueError, TypeError):
                    continue

        file_representation = getattr(self.instance, "file_representation", None)
        if file_representation is not None and file_representation.document is not None:
            return file_representation.document
        return None

    def _has_api_source(self):
        if self.is_bound:
            for key, value in self.data.items():
                if self.INLINE_API_BASE_URL_PATTERN.search(key) and (value or "").strip():
                    return True
        return getattr(self.instance, "api_representation", None) is not None

    def _suggested_resource_kind(self):
        current_kind = self.data.get(self.add_prefix("resource_kind")) or getattr(
            self.instance,
            "resource_kind",
            Resource.ResourceKind.DOCUMENT,
        )

        if self._has_api_source():
            return Resource.ResourceKind.API

        document = self._selected_document()
        if document is None:
            return current_kind

        return suggest_resource_kind_from_document(document, current_kind=current_kind)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        resource_kind_field = self.fields.get("resource_kind")
        storage_field = self.fields.get("storage_kind")
        metadata_field = self.fields.get("metadata")
        suggested_resource_kind = self._suggested_resource_kind()

        if resource_kind_field is not None:
            resource_kind_field.initial = suggested_resource_kind
            resource_kind_field.help_text = (
                "Suggested from the attached source when possible. "
                "CSV files with latitude/longitude columns are suggested as Spatial."
            )

            if self.is_bound:
                posted_resource_kind = self.data.get(self.add_prefix("resource_kind"), "")
                if posted_resource_kind in {"", Resource.ResourceKind.DOCUMENT}:
                    mutable_data = self.data.copy()
                    mutable_data[self.add_prefix("resource_kind")] = suggested_resource_kind
                    self.data = mutable_data

        if metadata_field is not None:
            metadata_field.help_text = (
                "Technical metadata managed by the system for ingestion, previews, and processing state."
            )
            metadata_field.widget.attrs["placeholder"] = json.dumps(
                getattr(self.instance, "metadata", {}) or {},
                indent=2,
                ensure_ascii=True,
            )

        if storage_field is None:
            return

        resource_kind = self.data.get(self.add_prefix("resource_kind")) or suggested_resource_kind

        if Resource.supports_postgres_storage(resource_kind):
            storage_field.choices = [
                (Resource.StorageKind.DEFAULT, "Default"),
                (Resource.StorageKind.DEFAULT_POSTGRES, "Default + Postgres"),
            ]
            storage_field.help_text = (
                "Tabular and spatial resources can keep the original file and also use Postgres."
            )
        else:
            storage_field.choices = [(Resource.StorageKind.DEFAULT, "Default")]
            storage_field.help_text = (
                "Only tabular and spatial resources can use Default + Postgres."
            )

    def clean(self):
        cleaned_data = super().clean()
        metadata = dict(cleaned_data.get("metadata") or {})
        if not metadata.get("created_by_display") and self.for_user is not None:
            metadata["created_by_display"] = self.instance.creator_display(fallback_user=self.for_user)
        cleaned_data["metadata"] = metadata
        return cleaned_data