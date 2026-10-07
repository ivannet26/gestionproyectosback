from rest_framework import viewsets

from apps.autenticacion.security import IsAdministrator
from .models import Area, Specialty
from .serializers import AreaSerializer, SpecialtySerializer


class AreaViewSet(viewsets.ModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsAdministrator]


class SpecialtyViewSet(viewsets.ModelViewSet):
    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer
    permission_classes = [IsAdministrator]

