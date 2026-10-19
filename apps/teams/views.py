from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.authentication.security import IsAdministrator
from apps.projects.services.audit import audit_actor
from apps.workers.services.areas import authorized_areas
from .models import Team, TeamMember
from .serializers import TeamMemberCreateSerializer, TeamMemberSerializer, TeamSerializer


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.select_related("area").order_by("id")
    serializer_class = TeamSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "members"):
            return [IsAuthenticated()]
        return [IsAdministrator()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.global_role != "ADMINISTRADOR":
            queryset = queryset.filter(area__in=authorized_areas(user.worker))
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
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search[:120])
        return queryset.annotate(active_members=Count("members", filter=Q(members__left_date__isnull=True)))

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        team = self.get_object()
        if request.method == "GET":
            members = TeamMember.objects.filter(team=team).select_related("worker").order_by("id")
            if request.query_params.get("all") not in ("1", "true"):
                members = members.filter(left_date__isnull=True)
            serializer = TeamMemberSerializer(members, many=True)
            return Response(serializer.data)
        serializer = TeamMemberCreateSerializer(data=request.data, context={"team": team})
        serializer.is_valid(raise_exception=True)
        worker_id = serializer.validated_data["worker_id"]
        joined_date = serializer.validated_data.get("joined_date") or timezone.localdate()
        with audit_actor(request.user), transaction.atomic():
            existing = TeamMember.objects.filter(team=team, worker_id=worker_id).order_by("-id").first()
            if existing is not None and existing.left_date is not None:
                existing.joined_date = joined_date
                existing.left_date = None
                try:
                    existing.save(update_fields=["joined_date", "left_date"])
                except IntegrityError:
                    return Response(
                        {"worker_id": "El trabajador ya pertenece al equipo"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                member = TeamMember.objects.select_related("worker").get(pk=existing.pk)
                return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)
            try:
                member = TeamMember.objects.create(team=team, worker_id=worker_id, joined_date=joined_date)
            except IntegrityError:
                return Response(
                    {"worker_id": "El trabajador ya pertenece al equipo"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            member = TeamMember.objects.select_related("worker").get(pk=member.pk)
            return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<member_id>\d+)")
    def remove_member(self, request, pk=None, member_id=None):
        team = self.get_object()
        member = TeamMember.objects.filter(pk=member_id, team=team, left_date__isnull=True).first()
        if member is None:
            return Response({"detail": "Miembro no disponible"}, status=status.HTTP_404_NOT_FOUND)
        with audit_actor(request.user), transaction.atomic():
            member.left_date = timezone.localdate()
            member.save(update_fields=["left_date"])
        return Response(status=status.HTTP_204_NO_CONTENT)
