from django.utils import timezone
from rest_framework import serializers

from apps.workers.models import Worker
from .models import Team, TeamMember


class TeamSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)
    active_members = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "area", "area_name", "name", "active", "active_members"]
        read_only_fields = ["id", "area_name", "active_members"]

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("El nombre es obligatorio")
        if len(cleaned) > 120:
            raise serializers.ValidationError("El nombre no puede superar 120 caracteres")
        return cleaned


class TeamMemberSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()

    class Meta:
        model = TeamMember
        fields = ["id", "worker", "worker_name", "joined_date", "left_date"]
        read_only_fields = ["id", "worker_name"]

    def get_worker_name(self, obj):
        worker = getattr(obj, "worker", None)
        if worker is None:
            return ""
        return f"{worker.first_names} {worker.last_names}".strip()


class TeamMemberCreateSerializer(serializers.Serializer):
    worker_id = serializers.IntegerField(min_value=1)
    joined_date = serializers.DateField(required=False, default=timezone.localdate)

    def validate_worker_id(self, value):
        worker = Worker.objects.filter(pk=value).first()
        if worker is None:
            raise serializers.ValidationError("Trabajador inexistente")
        if not worker.active:
            raise serializers.ValidationError("Trabajador inactivo")
        self.context["worker"] = worker
        return value

    def validate(self, attrs):
        team = self.context["team"]
        if not team.active:
            raise serializers.ValidationError({"team": "Equipo inactivo"})
        worker = self.context["worker"]
        if TeamMember.objects.filter(team=team, worker=worker, left_date__isnull=True).exists():
            raise serializers.ValidationError({"worker_id": "El trabajador ya pertenece al equipo"})
        if attrs.get("joined_date") and attrs["joined_date"] > timezone.localdate():
            raise serializers.ValidationError({"joined_date": "La fecha de ingreso no puede ser futura"})
        return attrs
