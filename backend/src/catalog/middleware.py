from urllib.parse import urlsplit

from django.conf import settings

from .pygeoapi import sync_pygeoapi_settings


class PygeoapiBootstrapMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        server_url = settings.PYGEOAPI_CONFIG.get("server", {}).get("url", "/geoapi/")
        self.base_path = urlsplit(server_url).path.rstrip("/") or "/geoapi"
        self.bootstrapped = False

    def __call__(self, request):
        if not self.bootstrapped and self._is_pygeoapi_request(request.path):
            self.bootstrapped = sync_pygeoapi_settings()

        return self.get_response(request)

    def _is_pygeoapi_request(self, path):
        normalized_path = (path or "").rstrip("/") or "/"
        return normalized_path == self.base_path or normalized_path.startswith(
            f"{self.base_path}/"
        )