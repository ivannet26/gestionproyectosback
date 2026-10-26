from django.urls import path

from .views import (
    PublicationCatalogView,
    PublicationApplyView,
    PublicationDetailView,
    PublicationListView,
    PublicationStateView,
)


urlpatterns = [
    path("", PublicationListView.as_view()),
    path("catalogs/", PublicationCatalogView.as_view()),
    path("<int:publication_id>/", PublicationDetailView.as_view()),
    path("<int:publication_id>/state/", PublicationStateView.as_view()),
    path("<int:publication_id>/apply/", PublicationApplyView.as_view()),
    path("<int:publication_id>/postular/", PublicationApplyView.as_view()),
    path("<int:publication_id>/solicitar/", PublicationApplyView.as_view()),
]
