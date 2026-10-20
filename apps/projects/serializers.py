from django.utils import timezone
from rest_framework import serializers

from apps.authentication.serializers import StrictSerializer


class ProjectFavoriteSerializer(StrictSerializer):
    is_favorite = serializers.BooleanField()


class LabelSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    kind = serializers.ChoiceField(choices=("technical", "nontechnical"))


class ProjectCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    area_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=1,
        error_messages={"empty": "Selecciona un área", "max_length": "Selecciona exactamente un área"},
    )
    mode = serializers.ChoiceField(choices=("available", "assigned"))
    worker_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list, max_length=200)
    worker_contribute = serializers.BooleanField(default=False)

    def validate(self, attrs):
        for key in ("area_ids", "worker_ids"):
            if len(attrs[key]) != len(set(attrs[key])):
                raise serializers.ValidationError({key: "No se permiten selecciones duplicadas"})
        if attrs["mode"] == "assigned" and not attrs["worker_ids"]:
            raise serializers.ValidationError(
                {"worker_ids": "Selecciona al menos un trabajador para crear con asignados"}
            )
        if attrs["mode"] == "available" and attrs["worker_ids"]:
            raise serializers.ValidationError({"worker_ids": "Publicar por área no asigna participantes"})
        if attrs["end_date"] is not None and attrs["end_date"] < timezone.localdate():
            raise serializers.ValidationError({"end_date": "La fecha final no puede ser anterior al inicio"})
        return attrs


def validate_labels(labels):
    keys = {(item["name"].casefold(), item["kind"]) for item in labels}
    if len(keys) != len(labels):
        raise serializers.ValidationError({"labels": "No se permiten etiquetas duplicadas"})


def validate_assignee_input(attrs, initial):
    ids = attrs.get("responsible_ids")
    if ids is not None:
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"responsible_ids": "No se permiten responsables duplicados"})
        if "responsible_id" in initial:
            expected = [] if attrs["responsible_id"] is None else [attrs["responsible_id"]]
            if set(ids) != set(expected):
                raise serializers.ValidationError({"responsible_ids": "Usa solo una forma de indicar los responsables"})


class TaskCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=180)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    state_code = serializers.CharField(max_length=20)
    priority = serializers.IntegerField(min_value=1, max_value=4, required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    responsible_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    responsible_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=200)
    parent_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    requirement_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list, max_length=50)
    labels = LabelSerializer(many=True, required=False, default=list, max_length=50)

    def validate(self, attrs):
        validate_assignee_input(attrs, self.initial_data)
        validate_labels(attrs["labels"])
        if len(attrs["requirement_ids"]) != len(set(attrs["requirement_ids"])):
            raise serializers.ValidationError({"requirement_ids": "No se permiten requisitos duplicados"})
        return attrs


class TaskEditSerializer(StrictSerializer):
    estimated_minutes = serializers.IntegerField(min_value=1, max_value=2147483647, allow_null=True, required=False)
    name = serializers.CharField(max_length=180, required=False)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    priority = serializers.IntegerField(min_value=1, max_value=4, required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    start_date = serializers.DateField(required=False)
    responsible_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    responsible_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=200)
    requirement_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=50)
    labels = LabelSerializer(many=True, required=False, max_length=50)

    def validate(self, attrs):
        validate_assignee_input(attrs, self.initial_data)
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


class TaskRelationSerializer(StrictSerializer):
    target_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=70)


class ProjectTaskStatusSerializer(StrictSerializer):
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=70)
    category = serializers.ChoiceField(choices=("not_started", "active", "done", "closed"), required=False)
    color = serializers.RegexField(r"^#[0-9a-fA-F]{6}$", required=False)


class StateReassignmentSerializer(StrictSerializer):
    source = serializers.CharField(max_length=20)
    target = serializers.CharField(max_length=20)
    reason = serializers.CharField(max_length=500, allow_blank=True, default="")


class TemplateStateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=70)
    category = serializers.ChoiceField(choices=("not_started", "active", "done", "closed"))
    color = serializers.RegexField(r"^#[0-9a-fA-F]{6}$")


class TaskStatusTemplateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=70)
    states = TemplateStateSerializer(many=True, max_length=50, allow_empty=True)
    revision = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        names = [state["name"].casefold() for state in attrs["states"]]
        if len(names) != len(set(names)):
            raise serializers.ValidationError({"states": "No se permiten nombres duplicados"})
        return attrs


class ProjectTaskConfigurationSerializer(StrictSerializer):
    template = serializers.ChoiceField(choices=("standard", "custom"))
    revision = serializers.CharField(min_length=64, max_length=64)
    states = ProjectTaskStatusSerializer(many=True, required=False, default=list, max_length=50)
    reassignments = StateReassignmentSerializer(many=True, default=list, max_length=50)

    def validate(self, attrs):
        states = attrs["states"]
        if attrs["template"] == "standard" and states:
            raise serializers.ValidationError({"states": "El modelo estándar no acepta estados personalizados"})
        if attrs["template"] == "custom" and not states:
            raise serializers.ValidationError({"states": "Configura al menos un estado"})
        codes = [state["code"] for state in states]
        names = [state["name"].casefold() for state in states]
        if len(codes) != len(set(codes)) or len(names) != len(set(names)):
            raise serializers.ValidationError({"states": "No se permiten códigos ni nombres duplicados"})
        sources = [item["source"] for item in attrs["reassignments"]]
        if len(sources) != len(set(sources)):
            raise serializers.ValidationError({"reassignments": "No se permiten orígenes duplicados"})
        return attrs
