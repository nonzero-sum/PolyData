import json

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Dataset, Resource, ResourceAPI, ResourceFile, ResourceTable
from .pygeoapi import sync_pygeoapi_settings
from ingestion.services import drop_resource_table_storage, process_resource


def _schedule_pygeoapi_sync(using=None):
    connection = transaction.get_connection(using=using)
    flag_name = "_catalog_pygeoapi_sync_scheduled"

    if getattr(connection, flag_name, False):
        return

    setattr(connection, flag_name, True)

    def _run_sync():
        setattr(connection, flag_name, False)
        sync_pygeoapi_settings()

    transaction.on_commit(_run_sync, using=using)


def _schedule_resource_processing(resource, using=None):
    if getattr(resource, "pk", None) is None:
        return

    connection = transaction.get_connection(using=using)
    flag_name = "_catalog_resource_processing_scheduled"
    scheduled_resource_ids = getattr(connection, flag_name, None)
    if scheduled_resource_ids is None:
        scheduled_resource_ids = set()
        setattr(connection, flag_name, scheduled_resource_ids)

    if resource.pk in scheduled_resource_ids:
        return

    scheduled_resource_ids.add(resource.pk)
    resource_pk = resource.pk

    def _run_processing():
        scheduled_resource_ids.discard(resource_pk)
        instance = Resource.objects.filter(pk=resource_pk).first()
        if instance is None:
            return
        _process_resource_if_needed(instance)

    transaction.on_commit(_run_processing, using=using)


def _is_parent_delete_cascade(kwargs):
    origin = kwargs.get("origin")
    if isinstance(origin, (Dataset, Resource)):
        return True

    origin_model = getattr(origin, "model", None)
    return origin_model in {Dataset, Resource}


def _handle_resource_source_save(resource, using=None):
    _schedule_resource_processing(resource, using=using)
    _schedule_pygeoapi_sync(using=using)


def _handle_resource_source_delete(resource, message, *, using=None, kwargs=None):
    if kwargs and _is_parent_delete_cascade(kwargs):
        _schedule_pygeoapi_sync(using=using)
        return

    _mark_resource_pending(resource, message)
    _schedule_resource_processing(resource, using=using)
    _schedule_pygeoapi_sync(using=using)


def _resource_has_processing_source(resource):
    if resource.file_items.exclude(document=None).exists():
        return True
    if resource.api_items.exists():
        return True
    if resource.tables.exists():
        return True
    return False


def _mark_resource_pending(resource, message):
    if resource.pk is None:
        return False

    updated = Resource.objects.filter(pk=resource.pk).update(
        processing_status=Resource.ProcessingStatus.PENDING,
        processing_message=message,
        processed_at=None,
    )
    if not updated:
        return False

    resource.processing_status = Resource.ProcessingStatus.PENDING
    resource.processing_message = message
    resource.processed_at = None
    return True


def _serialize_api_source(instance):
    return {
        "base_url": instance.base_url,
        "spec_type": instance.spec_type,
        "spec_url": instance.spec_url,
        "auth_type": instance.auth_type,
        "extra_config": json.dumps(instance.extra_config or {}, sort_keys=True),
    }


def _resource_source_changed(instance, field_names):
    if not instance.pk:
        return True

    previous = type(instance).objects.filter(pk=instance.pk).values(*field_names).first()
    if previous is None:
        return True

    current = {field_name: getattr(instance, field_name) for field_name in field_names}
    return any(previous.get(field_name) != current.get(field_name) for field_name in field_names)


def _process_resource_if_needed(resource):
    if resource.processing_status not in {
        Resource.ProcessingStatus.PENDING,
        Resource.ProcessingStatus.FAILED,
    }:
        return False

    if not _resource_has_processing_source(resource):
        return False

    updated = Resource.objects.filter(
        pk=resource.pk,
        processing_status__in=[
            Resource.ProcessingStatus.PENDING,
            Resource.ProcessingStatus.FAILED,
        ],
    ).update(
        processing_status=Resource.ProcessingStatus.PROCESSING,
        processing_message="Processing resource.",
    )
    if not updated:
        return False

    process_resource(Resource.objects.get(pk=resource.pk))
    return True


@receiver(pre_save, sender=ResourceFile)
def mark_resource_pending_before_file_change(sender, instance, **kwargs):
    if not _resource_source_changed(instance, ["document_id"]):
        return
    _mark_resource_pending(instance.resource, "Source file changed. Pending reprocessing.")


@receiver(pre_save, sender=ResourceAPI)
def mark_resource_pending_before_api_change(sender, instance, **kwargs):
    if not instance.pk:
        _mark_resource_pending(instance.resource, "API source changed. Pending reprocessing.")
        return

    previous = sender.objects.filter(pk=instance.pk).first()
    if previous is None:
        _mark_resource_pending(instance.resource, "API source changed. Pending reprocessing.")
        return

    if _serialize_api_source(previous) == _serialize_api_source(instance):
        return

    _mark_resource_pending(instance.resource, "API source changed. Pending reprocessing.")


@receiver(post_save, sender=Resource)
def process_resource_on_save(sender, instance, created, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_save(instance, using=using)


@receiver(post_delete, sender=Resource)
def sync_after_resource_delete(sender, instance, **kwargs):
    _schedule_pygeoapi_sync(using=kwargs.get("using"))


@receiver(post_save, sender=Dataset)
def sync_after_dataset_save(sender, instance, **kwargs):
    _schedule_pygeoapi_sync(using=kwargs.get("using"))


@receiver(post_delete, sender=Dataset)
def sync_after_dataset_delete(sender, instance, **kwargs):
    _schedule_pygeoapi_sync(using=kwargs.get("using"))


@receiver(post_save, sender=ResourceFile)
def process_file_representation_on_save(sender, instance, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_save(instance.resource, using=using)


@receiver(post_delete, sender=ResourceFile)
def sync_after_file_representation_delete(sender, instance, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_delete(
        instance.resource,
        "Source file removed. Awaiting reprocessing.",
        using=using,
        kwargs=kwargs,
    )


@receiver(post_save, sender=ResourceTable)
def process_table_representation_on_save(sender, instance, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_save(instance.resource, using=using)


@receiver(post_delete, sender=ResourceTable)
def sync_after_table_representation_delete(sender, instance, **kwargs):
    _schedule_pygeoapi_sync(using=kwargs.get("using"))


@receiver(pre_delete, sender=ResourceTable)
def drop_table_storage_before_resource_table_delete(sender, instance, **kwargs):
    drop_resource_table_storage(instance)


@receiver(post_save, sender=ResourceAPI)
def process_api_representation_on_save(sender, instance, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_save(instance.resource, using=using)


@receiver(post_delete, sender=ResourceAPI)
def sync_after_api_representation_delete(sender, instance, **kwargs):
    using = kwargs.get("using")
    _handle_resource_source_delete(
        instance.resource,
        "API source removed. Awaiting reprocessing.",
        using=using,
        kwargs=kwargs,
    )
