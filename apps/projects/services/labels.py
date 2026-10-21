from rest_framework.exceptions import ValidationError

from apps.organization.models import Specialty
from ..models import TaskLabel


def save_specialties(task, data):
    if "specialty_ids" not in data and "retained_label_ids" not in data:
        return
    if data.get("labels") or data.get("requirement_ids"):
        raise ValidationError({"labels": "No combines el selector de especialidades con etiquetas antiguas"})
    requested = data.get("specialty_ids", list(TaskLabel.objects.filter(task=task, specialty__isnull=False).values_list("specialty_id", flat=True)))
    specialties = list(Specialty.objects.select_for_update().filter(pk__in=requested))
    if len(specialties) != len(set(requested)):
        raise ValidationError({"specialty_ids": "Selecciona especialidades existentes"})
    old = TaskLabel.objects.filter(task=task, specialty__isnull=True)
    retained = data.get("retained_label_ids", list(old.values_list("pk", flat=True)))
    if set(retained) != set(old.filter(pk__in=retained).values_list("pk", flat=True)):
        raise ValidationError({"retained_label_ids": "La etiqueta histórica no pertenece a esta tarea"})
    if len(specialties) + len(retained) > 50:
        raise ValidationError({"specialty_ids": "Puedes incluir hasta 50 etiquetas"})
    TaskLabel.objects.filter(task=task, specialty__isnull=False).exclude(specialty_id__in=requested).delete()
    old.exclude(pk__in=retained).delete()
    existing = set(TaskLabel.objects.filter(task=task, specialty__isnull=False).values_list("specialty_id", flat=True))
    TaskLabel.objects.bulk_create([TaskLabel(task=task, specialty=item, name=f"specialty:{item.pk}", kind="specialty") for item in specialties if item.pk not in existing])
