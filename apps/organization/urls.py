from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AreaViewSet, SpecialtyViewSet

router = DefaultRouter()
router.register(r"areas", AreaViewSet)
router.register(r"specialties", SpecialtyViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
