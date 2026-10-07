from django.urls import include, path


urlpatterns = [
    path("api/auth/", include("apps.authentication.urls")),
    path("api/organization/", include("apps.organization.urls")),
    path("api/projects/", include("apps.projects.urls")),
    path("api/", include("apps.workers.urls")),
]