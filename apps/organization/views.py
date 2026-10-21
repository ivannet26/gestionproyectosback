from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError

from apps.authentication.security import IsAdministrator
from .models import Area, Specialty
from .serializers import AreaSerializer, SpecialtySerializer
from .services.areas import active_area_options


class AdminAreasView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        return Response(active_area_options())


class AreaViewSet(viewsets.ModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset()
        active = self.request.query_params.get("active")
        if active is not None:
            normalized = active.strip().lower()
            if normalized in ("true", "1"):
                queryset = queryset.filter(active=True)
            elif normalized in ("false", "0"):
                queryset = queryset.filter(active=False)
        return queryset


class SpecialtyViewSet(viewsets.ModelViewSet):
    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer
    permission_classes = [IsAdministrator]

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({"detail": "La especialidad está asociada a tareas. Retira sus asociaciones antes de eliminarla."}) from None

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        return queryset
