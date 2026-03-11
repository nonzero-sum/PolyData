from django.urls import include
from rest_framework import routers

from catalog.api import (
    DatasetViewSet,
    ResourceViewSet,
)

router = routers.DefaultRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("resources", ResourceViewSet, basename="resource")

urlpatterns = [
    path("", include(router.urls)),
]
