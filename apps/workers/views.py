from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.authentication.security import IsAdministrator
from .models import Worker
from .serializers import WorkerSerializer, WorkerSpecialtySerializer
from .services.specialties import handle_worker_specialties


class WorkerViewSet(viewsets.ModelViewSet):
    queryset = Worker.objects.select_related("area").prefetch_related("worker_specialties__specialty").order_by("id")
    serializer_class = WorkerSerializer
    permission_classes = [IsAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset()
        area_id = self.request.query_params.get("area_id")
        if area_id:
            queryset = queryset.filter(area_id=area_id)
        active = self.request.query_params.get("active")
        if active is not None:
            normalized = active.strip().lower()
            if normalized in ("true", "1"):
                queryset = queryset.filter(active=True)
            elif normalized in ("false", "0"):
                queryset = queryset.filter(active=False)
        return queryset

    @action(
        detail=False,
        methods=["get", "post", "delete"],
        url_path="me/specialties",
        permission_classes=[IsAuthenticated],
    )
    def me_specialties(self, request):
        return handle_worker_specialties(request.user.worker, request, None, WorkerSpecialtySerializer)

    @action(
        detail=False,
        methods=["post", "patch", "delete"],
        url_path=r"me/specialties/(?P<specialty_id>\d+)",
        permission_classes=[IsAuthenticated],
    )
    def me_specialty_detail(self, request, specialty_id=None):
        return handle_worker_specialties(request.user.worker, request, specialty_id, WorkerSpecialtySerializer)

    @action(detail=True, methods=["get", "post", "delete"], url_path="specialties")
    def specialties(self, request, pk=None):
        return handle_worker_specialties(self.get_object(), request, None, WorkerSpecialtySerializer)

    @action(
        detail=True,
        methods=["post", "patch", "delete"],
        url_path=r"specialties/(?P<specialty_id>\d+)",
    )
    def specialty_detail(self, request, pk=None, specialty_id=None):
        return handle_worker_specialties(self.get_object(), request, specialty_id, WorkerSpecialtySerializer)
