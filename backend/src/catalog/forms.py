import json

from django import forms

from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.documents.forms import BaseDocumentForm

from .file_formats import allowed_upload_extensions_accept, validate_allowed_upload
from .metadata_schemas import dublin_core_editable_fields, supported_metadata_schemas_display
from .models import Dataset, Resource


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
    class Meta:
        model = Dataset
        fields = "__all__"
        widgets = {
            "metadata": forms.HiddenInput(),
        }

    dc_subject = forms.CharField(required=False, label="Subject")
    dc_description = forms.CharField(required=False, label="Description", widget=forms.Textarea(attrs={"rows": 3}))
    dc_date = forms.CharField(required=False, label="Date")
    dc_type = forms.CharField(required=False, label="Type")
    dc_format = forms.CharField(required=False, label="Format")
    dc_source = forms.CharField(required=False, label="Source")
    dc_language = forms.CharField(required=False, label="Language")
    dc_relation = forms.CharField(required=False, label="Relation")
    dc_coverage = forms.CharField(required=False, label="Coverage")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        metadata_field = self.fields.get("metadata")
        if metadata_field is None:
            return

        metadata_initial = self.instance.get_dublin_core(fallback_user=self.for_user)
        metadata_field.initial = metadata_initial
        metadata_field.help_text = (
            "Editorial metadata for the dataset. "
            f"Supported schemas: {supported_metadata_schemas_display()}."
        )
        metadata_field.widget.attrs["placeholder"] = json.dumps(
            metadata_initial,
            indent=2,
            ensure_ascii=True,
        )

        metadata_fields = metadata_initial.get("fields", {})
        for field_name, _label in dublin_core_editable_fields():
            metadata_key = field_name.removeprefix("dc_")
            if field_name in self.fields:
                self.fields[field_name].initial = metadata_fields.get(metadata_key, "")

    def clean(self):
        cleaned_data = super().clean()
        self.instance.title = cleaned_data.get("title") or ""
        self.instance.slug = cleaned_data.get("slug") or ""
        self.instance.description = cleaned_data.get("description") or ""
        self.instance.organization = cleaned_data.get("organization")
        self.instance.license = cleaned_data.get("license")
        self.instance.set_dublin_core(
            {
                "schema": "dublincore",
                "fields": {
                    field_name.removeprefix("dc_"): cleaned_data.get(field_name, "") or ""
                    for field_name, _label in dublin_core_editable_fields()
                },
            },
            fallback_user=self.for_user,
        )
        cleaned_data["metadata"] = self.instance.metadata
        return cleaned_data


class ResourceForm(WagtailAdminModelForm):
    class Meta:
        model = Resource
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        storage_field = self.fields.get("storage_kind")
        metadata_field = self.fields.get("metadata")
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

        resource_kind = self.data.get(self.add_prefix("resource_kind")) or getattr(
            self.instance,
            "resource_kind",
            Resource.ResourceKind.DOCUMENT,
        )

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