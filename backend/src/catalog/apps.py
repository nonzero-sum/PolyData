from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"

    def ready(self):
        from .forms import DatasetForm, ResourceForm
        from .models import Dataset, Resource

        Dataset.base_form_class = DatasetForm
        Resource.base_form_class = ResourceForm
        from . import signals  # noqa: F401
