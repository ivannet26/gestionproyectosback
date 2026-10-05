from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


class ExplicitCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin == settings.FRONTEND_ORIGIN
        if request.method == "OPTIONS" and allowed:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRFToken"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            patch_vary_headers(response, ["Origin"])
        if request.path.startswith("/api/auth/"):
            response["Cache-Control"] = "no-store"
        return response
