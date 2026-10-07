from rest_framework import viewsets

from apps.autenticacion.security import IsAdministrator

from .models import Worker
from .serializers import WorkerSerializer


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
