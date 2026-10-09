from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/auth/", include("apps.authentication.urls")),
    path("api/organization/", include("apps.organization.urls")),
    path("api/projects/", include("apps.projects.urls")),
    path("api/", include("apps.workers.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
