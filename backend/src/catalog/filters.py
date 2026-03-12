import django_filters

from .models import Dataset, Organization, Resource


class OrganizationFilter(django_filters.FilterSet):
    class Meta:
        model = Organization
        fields = {}


class DatasetFilter(django_filters.FilterSet):
    organization = django_filters.CharFilter(method="filter_organization")
    tag = django_filters.CharFilter(field_name="tags__slug", lookup_expr="iexact")

    class Meta:
        model = Dataset
        fields = ["organization", "tag", "update_frequency"]

    def filter_organization(self, queryset, _name, value):
        normalized_value = (value or "").strip()
        if not normalized_value:
            return queryset
        return queryset.filter(organization__slug__iexact=normalized_value)


class ResourceFilter(django_filters.FilterSet):
    dataset = django_filters.NumberFilter(field_name="dataset_id")
    type = django_filters.CharFilter(field_name="resource_kind", lookup_expr="iexact")
    geospatial = django_filters.BooleanFilter(method="filter_geospatial")

    class Meta:
        model = Resource
        fields = ["dataset", "type", "geospatial", "processing_status"]

    def filter_geospatial(self, queryset, _name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(resource_kind=Resource.ResourceKind.SPATIAL)
        return queryset.exclude(resource_kind=Resource.ResourceKind.SPATIAL)