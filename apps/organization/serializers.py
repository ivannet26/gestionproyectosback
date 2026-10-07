from rest_framework import serializers

from .models import Area, Specialty


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ["id", "code", "name", "active"]
        read_only_fields = ["id"]


class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialty
        fields = ["id", "name"]
        read_only_fields = ["id"]
