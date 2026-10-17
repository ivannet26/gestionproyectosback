from rest_framework.exceptions import ValidationError

from ..models import ProjectMember, TaskAssignee
from .projects import eligible_project_workers


def task_assignee_ids(task):
    secondary = TaskAssignee.objects.filter(task=task).values_list("worker_id", flat=True)
    return sorted({*secondary, *([task.responsible_id] if task.responsible_id is not None else [])})


def requested_assignees(data, task=None):
    if "responsible_ids" in data:
        return sorted(data["responsible_ids"])
    if "responsible_id" in data:
        return [] if data["responsible_id"] is None else [data["responsible_id"]]
    return task_assignee_ids(task) if task else []


def validate_assignees(project, worker_ids, state_code, field="responsible_ids"):
    if not worker_ids:
        if state_code in ("EN_CURSO", "EN_REVISION", "COMPLETADA"):
            raise ValidationError({field: "Este estado requiere responsable activo del proyecto"})
        return
    allowed = set(ProjectMember.objects.filter(
        project=project, worker_id__in=worker_ids, active=True,
        worker__in=eligible_project_workers(project),
    ).values_list("worker_id", flat=True))
    if allowed != set(worker_ids):
        raise ValidationError({field: "Cada responsable debe ser participante activo del proyecto"})


def primary_assignee(worker_ids, task=None):
    if task and task.responsible_id in worker_ids:
        return task.responsible_id
    return worker_ids[0] if worker_ids else None


def save_assignees(task, worker_ids):
    extra = set(worker_ids) - {task.responsible_id}
    TaskAssignee.objects.filter(task=task).exclude(worker_id__in=extra).delete()
    existing = set(TaskAssignee.objects.filter(task=task).values_list("worker_id", flat=True))
    TaskAssignee.objects.bulk_create([
        TaskAssignee(task=task, worker_id=worker_id) for worker_id in sorted(extra - existing)
    ])
