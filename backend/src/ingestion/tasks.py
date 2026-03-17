from celery import shared_task

from catalog.models import Resource

from .services import process_resource


def _resource_has_processing_source(resource):
    if resource.file_items.exclude(document=None).exists():
        return True
    if resource.api_items.exists():
        return True
    if resource.tables.exists():
        return True
    return False


@shared_task(name="ingestion.process_resource")
def process_resource_task(resource_id):
    resource = Resource.objects.filter(pk=resource_id).first()
    if resource is None:
        return False

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