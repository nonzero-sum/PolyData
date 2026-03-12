from django.db.models import Prefetch
from django.views.generic import DetailView, ListView, TemplateView

from catalog.models import Dataset, DatasetTag, Organization, Resource
from catalog.serializers import ResourceTableSerializer


class HomeView(TemplateView):
    template_name = "main/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dataset_count"] = Dataset.objects.filter(resources__published=True).distinct().count()
        context["resource_count"] = Resource.objects.filter(published=True).count()
        context["organization_count"] = Organization.objects.filter(datasets__resources__published=True).distinct().count()
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        return context


class DatasetListView(ListView):
    model = Dataset
    template_name = "main/dataset_list.html"
    context_object_name = "datasets"
    paginate_by = 24

    def get_queryset(self):
        queryset = (
            Dataset.objects.select_related("organization", "license")
            .prefetch_related("tags")
            .filter(resources__published=True)
            .order_by("title")
        )
        search = (self.request.GET.get("search") or "").strip()
        selected_tag_slug = (self.request.GET.get("tag") or "").strip()
        if search:
            queryset = queryset.filter(title__icontains=search)
        if selected_tag_slug:
            queryset = queryset.filter(tags__slug=selected_tag_slug)
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        context["selected_tag_slug"] = (self.request.GET.get("tag") or "").strip()
        context["available_tags"] = DatasetTag.objects.filter(
            tagged_items__content_object__resources__published=True
        ).distinct().order_by("name")
        return context


class DatasetDetailView(DetailView):
    model = Dataset
    template_name = "main/dataset_detail.html"
    context_object_name = "dataset"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Dataset.objects.select_related("organization", "license").filter(resources__published=True).distinct().prefetch_related(
            Prefetch(
                "resources",
                queryset=Resource.objects.filter(published=True).prefetch_related(
                    "file_items",
                    "tables",
                    "api_items",
                ),
            ),
        )


class ResourceListView(ListView):
    model = Resource
    template_name = "main/resource_list.html"
    context_object_name = "resources"
    paginate_by = 24

    def get_queryset(self):
        queryset = (
            Resource.objects.select_related("dataset", "dataset__organization")
            .prefetch_related("file_items")
            .filter(published=True)
            .order_by("title")
        )
        search = (self.request.GET.get("search") or "").strip()
        selected_kind = (self.request.GET.get("kind") or "").strip()
        if search:
            queryset = queryset.filter(title__icontains=search)
        if selected_kind:
            queryset = queryset.filter(resource_kind=selected_kind)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("search") or "").strip()
        context["selected_kind"] = (self.request.GET.get("kind") or "").strip()
        context["available_resource_kinds"] = Resource.ResourceKind.choices
        return context


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
        ).filter(dataset__slug=self.kwargs["dataset_slug"], published=True)

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
        queryset = Organization.objects.filter(datasets__resources__published=True).distinct().order_by("title")
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
        return Organization.objects.filter(datasets__resources__published=True).distinct().prefetch_related(
            Prefetch(
                "datasets",
                queryset=Dataset.objects.select_related("license").filter(resources__published=True).distinct().prefetch_related(
                    Prefetch("resources", queryset=Resource.objects.filter(published=True))
                ),
            )
        )