from rest_framework.exceptions import ValidationError

from ..models import Area


def active_area_options():
    return list(Area.objects.filter(active=True).order_by("name").values("id", "name"))


def active_area_ids(ids):
    result = list(Area.objects.filter(active=True, pk__in=ids).values_list("pk", flat=True))
    if not ids or len(result) != len(ids):
        raise ValidationError({"area_ids": "Selecciona áreas activas válidas, sin duplicados"})
    return result
