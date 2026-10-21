from decimal import Decimal, localcontext
import hashlib
import json

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import APIException, ValidationError

from ..models import Task, TaskOrder
from .access import project_for_user, require_task_permission, task_for_user, tasks_for_user
from .audit import audit_actor, record_activity
from .tasks import apply_state_change, editable_project, validate_transition
from .statuses import configured_states


class MoveConflict(APIException):
    status_code = 409
    default_detail = "Las tareas cambiaron. Actualiza la lista antes de volver a mover."


def order_context(project):
    positions = dict(TaskOrder.objects.filter(task__project=project).values_list("task_id", "position"))
    rows = list(Task.objects.filter(project=project).order_by("pk").values_list("id", "parent_id", "state_code", "updated_at"))
    payload = [[pk, parent, state, str(updated), str(positions.get(pk, ""))] for pk, parent, state, updated in rows]
    revision = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return positions, revision


def ensure_positions(project):
    positions = dict(TaskOrder.objects.filter(task__project=project).values_list("task_id", "position"))
    maximum = max(positions.values(), default=Decimal(0))
    missing = []
    for pk in Task.objects.filter(project=project).order_by("id").values_list("pk", flat=True):
        if pk not in positions:
            maximum += 1024
            missing.append(TaskOrder(task_id=pk, position=maximum))
    TaskOrder.objects.bulk_create(missing)


def append_position(task):
    maximum = TaskOrder.objects.filter(task__project=task.project).aggregate(value=Max("position"))["value"] or Decimal(0)
    TaskOrder.objects.create(task=task, position=maximum + 1024)


def move_task(user, project_id, task_id, data):
    from .presentation import task_snapshots
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        editable_project(project)
        task = task_for_user(user, project, task_id)
        require_task_permission(user, project, task, "worker_state")
        positions, revision = order_context(project)
        if data["expected_revision"] != revision:
            raise MoveConflict()
        destination = data["state_code"]
        reason = ""
        changed = destination != task.state_code
        if changed:
            validate_transition(user, project, task, destination, reason, direct=True)
        elif destination not in {item["code"] for item in configured_states(project)}:
            raise ValidationError({"state_code": "El estado no está habilitado"})
        ensure_positions(project)
        siblings = list(Task.objects.filter(project=project, parent_id=task.parent_id, state_code=destination, archived=False).exclude(pk=task.pk).select_related("manual_order").order_by("manual_order__position", "id"))
        before = data["before_id"]
        if before is not None and not any(item.pk == before for item in siblings):
            raise ValidationError({"before_id": "La posición debe pertenecer al mismo grupo y padre"})
        if before is not None:
            task_for_user(user, project, before)
        index = next((index for index, item in enumerate(siblings) if item.pk == before), len(siblings))
        lower = siblings[index - 1].manual_order.position if index else None
        upper = siblings[index].manual_order.position if index < len(siblings) else None
        old_position = TaskOrder.objects.get(task=task).position
        if not changed:
            old_index = sum(item.manual_order.position < old_position for item in siblings)
            if old_index == index:
                return task_snapshots(tasks_for_user(user, project).select_related("responsible"), project, user)
        with localcontext() as context:
            context.prec = 50
            if lower is not None and upper is not None and upper - lower < Decimal("0.000000000000000002"):
                for number, sibling in enumerate(siblings, start=1):
                    sibling.manual_order.position = Decimal(number * 1024)
                TaskOrder.objects.bulk_update([item.manual_order for item in siblings], ["position"])
                lower = siblings[index - 1].manual_order.position if index else None
                upper = siblings[index].manual_order.position if index < len(siblings) else None
            position = (lower + upper) / 2 if lower is not None and upper is not None else upper - 1024 if upper is not None else (lower or Decimal(0)) + 1024
        if changed:
            apply_state_change(project, task, destination, reason, nested=True, direct=True)
        TaskOrder.objects.filter(task=task).update(position=position)
        if old_position != position:
            record_activity(task, "changed", field="position", old=str(old_position), new=str(position))
        return task_snapshots(tasks_for_user(user, project).select_related("responsible"), project, user)
