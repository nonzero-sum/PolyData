from django.views.generic import DetailView, ListView, TemplateView

from catalog.models import Dataset, Organization, Resource
from catalog.serializers import ResourceTableSerializer


class HomeView(TemplateView):
    template_name = "main/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dataset_count"] = Dataset.objects.count()
        context["organization_count"] = Organization.objects.count()
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        return context


class DatasetListView(ListView):
    model = Dataset
    template_name = "main/dataset_list.html"
    context_object_name = "datasets"
    paginate_by = 24

    def get_queryset(self):
        queryset = Dataset.objects.select_related("organization", "license").order_by("title")
        search = (self.request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        return context


class DatasetDetailView(DetailView):
    model = Dataset
    template_name = "main/dataset_detail.html"
    context_object_name = "dataset"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Dataset.objects.select_related("organization", "license").prefetch_related(
            "resources__file_items",
            "resources__tables",
            "resources__api_items",
        )


class ResourceDetailView(DetailView):
    model = Resource
    template_name = "main/resource_detail.html"
    context_object_name = "resource"
    slug_field = "slug"
    slug_url_kwarg = "resource_slug"

    def get_queryset(self):
        return Resource.objects.select_related("dataset", "dataset__organization", "dataset__license").prefetch_related(
            "file_items",
            "tables",
            "api_items",
        ).filter(dataset__slug=self.kwargs["dataset_slug"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tables_data"] = ResourceTableSerializer(
            self.object.tables.order_by("-is_primary", "layer_name", "table_name"),
            many=True,
            context={"request": self.request},
        ).data
        return context


class OrganizationListView(ListView):
    model = Organization
    template_name = "main/organization_list.html"
    context_object_name = "organizations"
    paginate_by = 24

    def get_queryset(self):
        queryset = Organization.objects.order_by("title")
        search = (self.request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        return context


class OrganizationDetailView(DetailView):
    model = Organization
    template_name = "main/organization_detail.html"
    context_object_name = "organization"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Organization.objects.prefetch_related("datasets__license", "datasets__resources")