from django.db import transaction
from rest_framework import serializers

from .models import Worker, WorkerSpecialty


class WorkerSpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerSpecialty
        fields = ["specialty", "level"]


class WorkerSerializer(serializers.ModelSerializer):
    specialties = WorkerSpecialtySerializer(many=True, required=False, source="worker_specialties")

    class Meta:
        model = Worker
        fields = [
            "id",
            "area",
            "code",
            "first_names",
            "last_names",
            "email",
            "weekly_hours",
            "active",
            "all_areas",
            "specialties",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        specialties_data = validated_data.pop("worker_specialties", [])
        with transaction.atomic():
            worker = Worker.objects.create(**validated_data)
            self._replace_specialties(worker, specialties_data)
        return worker

    def update(self, instance, validated_data):
        specialties_data = validated_data.pop("worker_specialties", None)
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if specialties_data is not None:
                self._replace_specialties(instance, specialties_data)
        return instance

    def _replace_specialties(self, worker, specialties_data):
        WorkerSpecialty.objects.filter(worker=worker).delete()
        WorkerSpecialty.objects.bulk_create(
            [
                WorkerSpecialty(worker=worker, specialty=item["specialty"], level=item.get("level", 1))
                for item in specialties_data
            ]
        )
