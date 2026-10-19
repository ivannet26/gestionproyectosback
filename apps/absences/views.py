from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.authentication.security import IsAdministrator
from apps.projects.services.audit import audit_actor
from .models import Absence
from .serializers import AbsenceCreateSerializer, AbsenceReviewSerializer, AbsenceSerializer


class AbsenceViewSet(viewsets.ModelViewSet):
    queryset = Absence.objects.select_related("worker").order_by("id")
    serializer_class = AbsenceSerializer
    permission_classes = [IsAdministrator]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdministrator()]

    def get_serializer_class(self):
        if self.action == "create":
            return AbsenceCreateSerializer
        return AbsenceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get("status", "").strip().lower()
        if status == "anulada":
            queryset = queryset.filter(anulada=True)
        elif status == "aprobada":
            queryset = queryset.filter(aprobada=True, anulada=False)
        elif status == "pendiente":
            queryset = queryset.filter(aprobada__isnull=True, anulada=False)
        search = self.request.query_params.get("search", "").strip()
        for word in search.split():
            queryset = queryset.filter(
                Q(worker__first_names__icontains=word)
                | Q(worker__last_names__icontains=word)
                | Q(motivo__icontains=word)
            )
        return queryset

    @action(detail=True, methods=["patch"], url_path="review")
    def review(self, request, pk=None):
        absence = self.get_object()
        if absence.anulada:
            raise ValidationError("La ausencia ya fue anulada.")
        if absence.aprobada is not None:
            raise ValidationError("La ausencia ya fue revisada.")
        payload = AbsenceReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with audit_actor(request.user), transaction.atomic():
            if payload.validated_data["aprobada"]:
                absence.aprobada = True
            else:
                absence.anulada = True
            absence.save(update_fields=["aprobada", "anulada"])
        return Response(AbsenceSerializer(absence).data)

    def create(self, request, *args, **kwargs):
        worker = getattr(request.user, "worker", None)
        if worker is None:
            raise ValidationError("Tu cuenta no tiene trabajador asociado.")
        payload = AbsenceCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with audit_actor(request.user), transaction.atomic():
            absence = Absence.objects.create(worker=worker, **payload.validated_data)
        return Response(AbsenceSerializer(absence).data, status=status.HTTP_201_CREATED)
