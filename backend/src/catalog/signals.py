from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models import Dataset, Resource, ResourceAPI, ResourceFile, ResourceTable
from .pygeoapi import sync_pygeoapi_settings
from .services import drop_resource_table_storage, process_resource


@receiver(post_save, sender=Resource)
def process_resource_on_save(sender, instance, created, **kwargs):
    process_resource(instance)
    sync_pygeoapi_settings()


@receiver(post_delete, sender=Resource)
def sync_after_resource_delete(sender, instance, **kwargs):
    sync_pygeoapi_settings()


@receiver(post_save, sender=Dataset)
def sync_after_dataset_save(sender, instance, **kwargs):
    sync_pygeoapi_settings()


@receiver(post_delete, sender=Dataset)
def sync_after_dataset_delete(sender, instance, **kwargs):
    sync_pygeoapi_settings()


@receiver(post_save, sender=ResourceFile)
def process_file_representation_on_save(sender, instance, **kwargs):
    process_resource(instance.resource)
    sync_pygeoapi_settings()


@receiver(post_delete, sender=ResourceFile)
def sync_after_file_representation_delete(sender, instance, **kwargs):
    process_resource(instance.resource)
    sync_pygeoapi_settings()


@receiver(post_save, sender=ResourceTable)
def process_table_representation_on_save(sender, instance, **kwargs):
    process_resource(instance.resource)
    sync_pygeoapi_settings()


@receiver(post_delete, sender=ResourceTable)
def sync_after_table_representation_delete(sender, instance, **kwargs):
    sync_pygeoapi_settings()


@receiver(pre_delete, sender=ResourceTable)
def drop_table_storage_before_resource_table_delete(sender, instance, **kwargs):
    drop_resource_table_storage(instance)


@receiver(post_save, sender=ResourceAPI)
def process_api_representation_on_save(sender, instance, **kwargs):
    process_resource(instance.resource)
    sync_pygeoapi_settings()


@receiver(post_delete, sender=ResourceAPI)
def sync_after_api_representation_delete(sender, instance, **kwargs):
    process_resource(instance.resource)
    sync_pygeoapi_settings()
