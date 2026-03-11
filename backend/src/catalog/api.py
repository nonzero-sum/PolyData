from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import Dataset, Resource, ResourceTable
from .serializers import (
    DatasetSerializer,
    ResourceAPISerializer,
    ResourceFileSerializer,
    ResourceSerializer,
    ResourceTableSerializer,
)
from .services import fetch_resource_table_rows, get_primary_resource_table


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

    def _get_nested_table(self, resource, table_pk):
        try:
            return resource.tables.get(pk=table_pk)
        except ResourceTable.DoesNotExist as error:
            raise NotFound("This resource does not have a derived table with that id.") from error

    def _get_nested_file(self, resource, file_pk):
        try:
            return resource.file_items.get(pk=file_pk)
        except resource.file_items.model.DoesNotExist as error:
            raise NotFound("This resource does not have a file with that id.") from error

    def _get_nested_api(self, resource, api_pk):
        try:
            return resource.api_items.get(pk=api_pk)
        except resource.api_items.model.DoesNotExist as error:
            raise NotFound("This resource does not have an API representation with that id.") from error

    @action(detail=True, methods=["get"])
    def files(self, request, pk=None):
        resource = self.get_object()
        queryset = resource.file_items.all()

        page = self.paginate_queryset(queryset)
        serializer = ResourceFileSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"files/(?P<file_pk>[^/.]+)")
    def file_detail(self, request, pk=None, file_pk=None):
        resource = self.get_object()
        resource_file = self._get_nested_file(resource, file_pk)
        serializer = ResourceFileSerializer(
            resource_file,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def tables(self, request, pk=None):
        resource = self.get_object()
        queryset = resource.tables.order_by("-is_primary", "layer_name", "table_name")

        page = self.paginate_queryset(queryset)
        serializer = ResourceTableSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"tables/(?P<table_pk>[^/.]+)")
    def table_detail(self, request, pk=None, table_pk=None):
        resource = self.get_object()
        resource_table = self._get_nested_table(resource, table_pk)
        serializer = ResourceTableSerializer(
            resource_table,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"tables/(?P<table_pk>[^/.]+)/rows")
    def table_rows(self, request, pk=None, table_pk=None):
        resource = self.get_object()
        resource_table = self._get_nested_table(resource, table_pk)

        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 10))
        except ValueError as error:
            raise ValidationError("page and page_size must be integers.") from error

        payload = fetch_resource_table_rows(
            resource_table,
            page=page,
            page_size=page_size,
        )
        payload["table"] = ResourceTableSerializer(
            resource_table,
            context=self.get_serializer_context(),
        ).data
        return Response(payload)

    @action(detail=True, methods=["get"])
    def apis(self, request, pk=None):
        resource = self.get_object()
        queryset = resource.api_items.all()

        page = self.paginate_queryset(queryset)
        serializer = ResourceAPISerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"apis/(?P<api_pk>[^/.]+)")
    def api_detail(self, request, pk=None, api_pk=None):
        resource = self.get_object()
        resource_api = self._get_nested_api(resource, api_pk)
        serializer = ResourceAPISerializer(
            resource_api,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def table(self, request, pk=None):
        resource = self.get_object()
        resource_table = get_primary_resource_table(resource)
        if resource_table is None:
            raise NotFound("This resource does not have a derived table.")

        serializer = ResourceTableSerializer(
            resource_table,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def rows(self, request, pk=None):
        resource = self.get_object()
        resource_table = get_primary_resource_table(resource)
        if resource_table is None:
            raise NotFound("This resource does not have a derived table.")

        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 10))
        except ValueError as error:
            raise ValidationError("page and page_size must be integers.") from error

        payload = fetch_resource_table_rows(
            resource_table,
            page=page,
            page_size=page_size,
        )
        payload["table"] = ResourceTableSerializer(
            resource_table,
            context=self.get_serializer_context(),
        ).data
        return Response(payload)
