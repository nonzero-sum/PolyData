from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Dataset, Resource, ResourceAPI, ResourceFile, ResourceTable
from .serializers import (
    DatasetSerializer,
    ResourceAPISerializer,
    ResourceFileSerializer,
    ResourceSerializer,
    ResourceTableSerializer,
)


class DatasetViewSet(viewsets.ModelViewSet):
    queryset = Dataset.objects.prefetch_related(
        "resources__file_items",
        "resources__tables",
        "resources__api_items",
    ).all()
    serializer_class = DatasetSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        organization = self.request.query_params.get("organization", "").strip()
        if search:
            queryset = queryset.filter(title__icontains=search)
        if organization:
            queryset = queryset.filter(organization__slug__iexact=organization)
        return queryset

    @action(detail=True, methods=["get"])
    def resources(self, request, pk=None):
        dataset = self.get_object()
        queryset = dataset.resources.all()

        resource_type = request.query_params.get("type", "").strip()
        if resource_type:
            queryset = queryset.filter(resource_kind=resource_type)

        page = self.paginate_queryset(queryset)
        serializer = ResourceSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class ResourceViewSet(viewsets.ModelViewSet):
    queryset = Resource.objects.select_related("dataset").prefetch_related(
        "file_items",
        "tables",
        "api_items",
    ).all()
    serializer_class = ResourceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        dataset_id = self.request.query_params.get("dataset")
        resource_type = self.request.query_params.get("type", "").strip()
        geospatial = self.request.query_params.get("geospatial", "").strip().lower()

        if dataset_id:
            queryset = queryset.filter(dataset_id=dataset_id)
        if resource_type:
            queryset = queryset.filter(resource_kind=resource_type)
        if geospatial in {"1", "true", "yes"}:
            queryset = queryset.filter(resource_kind=Resource.ResourceKind.SPATIAL)

        return queryset


class ResourceFileViewSet(viewsets.ModelViewSet):
    queryset = ResourceFile.objects.select_related("resource", "resource__dataset").all()
    serializer_class = ResourceFileSerializer


class ResourceTableViewSet(viewsets.ModelViewSet):
    queryset = ResourceTable.objects.select_related("resource", "resource__dataset").all()
    serializer_class = ResourceTableSerializer


class ResourceAPIViewSet(viewsets.ModelViewSet):
    queryset = ResourceAPI.objects.select_related("resource", "resource__dataset").all()
    serializer_class = ResourceAPISerializer
