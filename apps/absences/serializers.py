from rest_framework import serializers

from .models import Absence


class AbsenceSerializer(serializers.ModelSerializer):
    trabajador_id = serializers.IntegerField(source="worker_id", read_only=True)
    trabajador_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Absence
        fields = [
            "id",
            "trabajador_id",
            "trabajador_nombre",
            "fecha_inicio",
            "fecha_fin",
            "motivo",
            "anulada",
            "aprobada",
        ]
        read_only_fields = fields

    def get_trabajador_nombre(self, obj: Absence) -> str:
        return f"{obj.worker.first_names} {obj.worker.last_names}".strip()


class AbsenceReviewSerializer(serializers.Serializer):
    aprobada = serializers.BooleanField()


class AbsenceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Absence
        fields = ["fecha_inicio", "fecha_fin", "motivo"]

    def validate(self, attrs):
        if attrs["fecha_fin"] < attrs["fecha_inicio"]:
            raise serializers.ValidationError("La fecha de fin es anterior a la de inicio.")
        return attrs
