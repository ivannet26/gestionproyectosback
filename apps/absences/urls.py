from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AbsenceViewSet

router = DefaultRouter()
router.register(r"absences", AbsenceViewSet, basename="absence")

urlpatterns = [
    path("", include(router.urls)),
]
