from rest_framework import serializers

from apps.authentication.serializers import StrictSerializer


class LabelSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    kind = serializers.ChoiceField(choices=("technical", "nontechnical"))


class ProjectCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    area_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=100)
    requirements = LabelSerializer(many=True, required=False, default=list, max_length=50)
    mode = serializers.ChoiceField(choices=("available", "assigned"))
    worker_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list, max_length=200)
    worker_edit = serializers.BooleanField(default=False)
    worker_state = serializers.BooleanField(default=False)

    def validate(self, attrs):
        for key in ("area_ids", "worker_ids"):
            if len(attrs[key]) != len(set(attrs[key])):
                raise serializers.ValidationError({key: "No se permiten selecciones duplicadas"})
        if attrs["mode"] == "assigned" and (not attrs["worker_ids"] or not attrs["start_date"] or not attrs["end_date"]):
            raise serializers.ValidationError({"detail": "Selecciona trabajadores y ambas fechas para crear con asignados"})
        if attrs["mode"] == "available" and attrs["worker_ids"]:
            raise serializers.ValidationError({"worker_ids": "Publicar por áreas no asigna participantes"})
        if attrs["start_date"] and attrs["end_date"] and attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "La fecha final no puede ser anterior al inicio"})
        validate_labels(attrs["requirements"])
        return attrs


def validate_labels(labels):
    keys = {(item["name"].casefold(), item["kind"]) for item in labels}
    if len(keys) != len(labels):
        raise serializers.ValidationError({"labels": "No se permiten etiquetas duplicadas"})


class TaskCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=180)
    state_code = serializers.CharField(max_length=20)
    priority = serializers.IntegerField(min_value=1, max_value=4)
    due_date = serializers.DateField()
    responsible_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    parent_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    requirement_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list, max_length=50)
    labels = LabelSerializer(many=True, required=False, default=list, max_length=50)

    def validate(self, attrs):
        validate_labels(attrs["labels"])
        if len(attrs["requirement_ids"]) != len(set(attrs["requirement_ids"])):
            raise serializers.ValidationError({"requirement_ids": "No se permiten requisitos duplicados"})
        return attrs


class TaskEditSerializer(StrictSerializer):
    name = serializers.CharField(max_length=180, required=False)
    priority = serializers.IntegerField(min_value=1, max_value=4, required=False)
    due_date = serializers.DateField(required=False)
    responsible_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    requirement_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=50)
    labels = LabelSerializer(many=True, required=False, max_length=50)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"detail": "Indica los datos que quieres modificar"})
        if "labels" in attrs:
            validate_labels(attrs["labels"])
        ids = attrs.get("requirement_ids", [])
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"requirement_ids": "No se permiten requisitos duplicados"})
        return attrs


class TaskStateSerializer(StrictSerializer):
    state_code = serializers.CharField(max_length=20)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DependencySerializer(StrictSerializer):
    predecessor_id = serializers.IntegerField(min_value=1)
