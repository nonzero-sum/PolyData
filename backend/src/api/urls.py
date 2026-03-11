from django.urls import include, path
from rest_framework import routers

from catalog.api import (
    DatasetViewSet,
    ResourceAPIViewSet,
    ResourceFileViewSet,
    ResourceTableViewSet,
    ResourceViewSet,
)

router = routers.DefaultRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("resources", ResourceViewSet, basename="resource")
router.register("resource-files", ResourceFileViewSet, basename="resource-file")
router.register("resource-tables", ResourceTableViewSet, basename="resource-table")
router.register("resource-apis", ResourceAPIViewSet, basename="resource-api")

urlpatterns = [
    path("", include(router.urls)),
]
