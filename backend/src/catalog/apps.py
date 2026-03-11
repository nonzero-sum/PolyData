from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.utils import OperationalError, ProgrammingError


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"

    def _ensure_resource_schema_on_connection(self, sender, connection, **kwargs):
        schema_name = (settings.RESOURCE_DATA_SCHEMA or "resource_data").strip() or "resource_data"
        quoted_schema_name = connection.ops.quote_name(schema_name)

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema_name}")
        except (OperationalError, ProgrammingError):
            pass

    def ready(self):
        from .forms import DatasetForm, ResourceForm
        from .models import Dataset, Resource

        Dataset.base_form_class = DatasetForm
        Resource.base_form_class = ResourceForm
        connection_created.connect(
            self._ensure_resource_schema_on_connection,
            dispatch_uid="catalog.ensure_resource_data_schema",
        )
        from . import signals  # noqa: F401
