from wagtail import hooks
from wagtail.admin.menu import Menu, SubmenuMenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Dataset, Resource


class DatasetSnippetViewSet(SnippetViewSet):
    model = Dataset
    icon = "folder-open-inverse"
    add_to_admin_menu = True
    menu_label = "Datasets"
    menu_name = "catalog_datasets"
    menu_order = 310
    list_display = ["title", "organization", "update_frequency", "updated_at"]
    search_fields = ["title", "description", "slug"]
    ordering = ["title"]


class ResourceSnippetViewSet(SnippetViewSet):
    model = Resource
    icon = "doc-full-inverse"
    add_to_admin_menu = True
    menu_label = "Resources"
    menu_name = "catalog_resources"
    menu_order = 311
    list_display = ["title", "dataset", "resource_kind", "storage_kind", "updated_at"]
    search_fields = ["title", "description", "slug", "dataset__title"]
    ordering = ["dataset__title", "title"]


register_snippet(DatasetSnippetViewSet)
register_snippet(ResourceSnippetViewSet)


@hooks.register("construct_main_menu")
def group_files_menu_items(request, menu_items):
    files_item_names = ["images", "documents"]
    files_items = [item for item in menu_items if item.name in files_item_names]
    if not files_items:
        return

    menu_items[:] = [item for item in menu_items if item.name not in files_item_names]

    submenu = SubmenuMenuItem(
        "Files",
        Menu(items=files_items),
        name="files",
        icon_name="folder-open-inverse",
        order=min(item.order for item in files_items),
    )
    menu_items.append(submenu)