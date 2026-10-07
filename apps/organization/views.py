from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

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


class SpecialtyViewSet(viewsets.ModelViewSet):
    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer
    permission_classes = [IsAdministrator]

