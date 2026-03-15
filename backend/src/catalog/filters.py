import django_filters
from django.db.models import Q
from paradedb.functions import Score
from paradedb.search import Match, ParadeDB

from .models import Dataset, Organization, Resource


class OrganizationFilter(django_filters.FilterSet):
    class Meta:
        model = Organization
        fields = {}


class DatasetFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    q = django_filters.CharFilter(method="filter_search")
    organization = django_filters.CharFilter(method="filter_organization")
    tag = django_filters.CharFilter(field_name="tags__slug", lookup_expr="iexact")

    class Meta:
        model = Dataset
        fields = ["search", "q", "organization", "tag", "update_frequency"]

    def filter_search(self, queryset, _name, value):
        normalized_value = (value or "").strip()
        if not normalized_value:
            return queryset
        return (
            queryset.filter(
                Q(title=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(description=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(dc_subject=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(dc_description=ParadeDB(Match(normalized_value, operator="AND")))
            )
            .annotate(score=Score())
            .order_by("-score")
        )

    def filter_organization(self, queryset, _name, value):
        normalized_value = (value or "").strip()
        if not normalized_value:
            return queryset
        return queryset.filter(organization__slug__iexact=normalized_value)


class ResourceFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    q = django_filters.CharFilter(method="filter_search")
    dataset = django_filters.NumberFilter(field_name="dataset_id")
    type = django_filters.CharFilter(field_name="resource_kind", lookup_expr="iexact")
    tag = django_filters.CharFilter(method="filter_tag")
    geospatial = django_filters.BooleanFilter(method="filter_geospatial")

    class Meta:
        model = Resource
        fields = ["search", "q", "dataset", "type", "tag", "geospatial"]

    def filter_search(self, queryset, _name, value):
        normalized_value = (value or "").strip()
        if not normalized_value:
            return queryset
        return (
            queryset.filter(
                Q(title=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(description=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(media_type=ParadeDB(Match(normalized_value, operator="AND")))
                | Q(metadata=ParadeDB(Match(normalized_value, operator="AND")))
            )
            .annotate(score=Score())
            .order_by("-score")
        )

    def filter_tag(self, queryset, _name, value):
        normalized_value = (value or "").strip()
        if not normalized_value:
            return queryset
        return queryset.filter(dataset__tags__slug__iexact=normalized_value).distinct()

    def filter_geospatial(self, queryset, _name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(resource_kind=Resource.ResourceKind.SPATIAL)
        return queryset.exclude(resource_kind=Resource.ResourceKind.SPATIAL)