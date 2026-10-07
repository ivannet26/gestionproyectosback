from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ..models import ProjectMember, ProjectRequirement, Task, TaskDependency, TaskLabel, TaskState, TaskTransition
from ..serializers import validate_labels
from .access import project_for_user, require_admin, require_task_permission, task_for_user
from .audit import audit_actor


def editable_project(project):
    if project.state_code in ("FINALIZADO", "CANCELADO"):
        raise ValidationError({"detail": "El proyecto está cerrado"})


def validate_responsible(project, worker_id, state_code):
    if worker_id is None:
        if state_code in ("EN_CURSO", "EN_REVISION", "COMPLETADA"):
            raise ValidationError({"responsible_id": "Este estado requiere responsable activo del proyecto"})
        return
    if not ProjectMember.objects.filter(project=project, worker_id=worker_id, active=True, worker__active=True).exists():
        raise ValidationError({"responsible_id": "El responsable debe ser participante activo del proyecto"})


def validate_dates(project, start_date, due_date, parent=None, task=None):
    if due_date < start_date or (project.end_date and due_date > project.end_date):
        raise ValidationError({"due_date": "La fecha límite queda fuera del periodo permitido"})
    if project.start_date and start_date < project.start_date:
        raise ValidationError({"due_date": "La tarea debe respetar el inicio del proyecto"})
    if parent and (start_date < parent.start_date or due_date > parent.due_date):
        raise ValidationError({"due_date": "La subtarea debe quedar dentro del periodo de su tarea padre"})
    if task and Task.objects.filter(parent=task, archived=False, due_date__gt=due_date).exists():
        raise ValidationError({"due_date": "La fecha dejaría subtareas fuera del periodo padre"})


def save_labels(task, data):
    if "labels" not in data and "requirement_ids" not in data:
        return
    ids = data.get("requirement_ids", list(TaskLabel.objects.filter(task=task, requirement__isnull=False).values_list("requirement_id", flat=True)))
    own = data.get("labels", list(TaskLabel.objects.filter(task=task, requirement__isnull=True).values("name", "kind")))
    requirements = list(ProjectRequirement.objects.filter(project=task.project, pk__in=ids))
    if len(requirements) != len(ids):
        raise ValidationError({"requirement_ids": "Los requisitos deben pertenecer al proyecto"})
    labels = [{"name": item.name, "kind": item.kind} for item in requirements] + own
    validate_labels(labels)
    TaskLabel.objects.filter(task=task).delete()
    TaskLabel.objects.bulk_create(
        [TaskLabel(task=task, requirement=item, name=item.name, kind=item.kind) for item in requirements]
        + [TaskLabel(task=task, **label) for label in own]
    )


def create_task(user, project_id, data):
    require_admin(user)
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        editable_project(project)
        if not TaskState.objects.filter(pk=data["state_code"]).exists():
            raise ValidationError({"state_code": "Estado no válido"})
        if data["state_code"] in ("BLOQUEADA", "CANCELADA") and not data["reason"]:
            raise ValidationError({"reason": "Indica un motivo para este estado"})
        parent = None
        if data["parent_id"]:
            parent = Task.objects.filter(project=project, pk=data["parent_id"], archived=False).first()
            if parent is None or parent.state_code in ("COMPLETADA", "CANCELADA"):
                raise ValidationError({"parent_id": "La tarea padre no está disponible en este proyecto"})
        start_date = parent.start_date if parent else project.start_date or timezone.localdate()
        validate_dates(project, start_date, data["due_date"], parent=parent)
        validate_responsible(project, data["responsible_id"], data["state_code"])
        task = Task.objects.create(
            project=project, parent=parent, phase_id=parent.phase_id if parent else None,
            name=data["name"], state_code=data["state_code"], priority=data["priority"],
            start_date=start_date, due_date=data["due_date"], responsible_id=data["responsible_id"],
            reason=data["reason"] or None, progress=100 if data["state_code"] == "COMPLETADA" else 0,
        )
        save_labels(task, data)
    return task


def edit_task(user, project_id, task_id, data):
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        task = task_for_user(user, project, task_id)
        require_task_permission(user, project, task, "worker_edit")
        editable_project(project)
        if "responsible_id" in data:
            require_admin(user)
        parent = task.parent if task.parent_id else None
        validate_dates(project, task.start_date, data.get("due_date", task.due_date), parent=parent, task=task)
        validate_responsible(project, data.get("responsible_id", task.responsible_id), task.state_code)
        for field in ("name", "priority", "due_date", "responsible_id"):
            if field in data:
                setattr(task, field, data[field])
        task.updated_at = timezone.now()
        task.save()
        save_labels(task, data)
    return task


def has_supervision(user, project):
    return user.global_role == "ADMINISTRADOR" or ProjectMember.objects.filter(
        project=project, worker_id=user.worker_id, active=True, project_role__in=("RESPONSABLE", "REVISOR"),
    ).exists()


def validate_transition(user, project, task, target, reason):
    editable_project(project)
    if project.state_code not in ("PLANIFICADO", "EN_CURSO") and target != "CANCELADA":
        raise ValidationError({"detail": "El proyecto no permite ejecutar tareas en su estado actual"})
    transition = TaskTransition.objects.filter(source=task.state_code, target=target).first()
    if transition is None:
        raise ValidationError({"state_code": "La transición no está permitida"})
    if transition.supervision_required and not has_supervision(user, project):
        raise PermissionDenied("Esta transición requiere supervisión del proyecto")
    if transition.reason_required and not reason:
        raise ValidationError({"reason": "Indica el motivo del cambio"})
    validate_responsible(project, task.responsible_id, target)
    if target not in ("COMPLETADA", "CANCELADA"):
        parent = task.parent
        visited = set()
        while parent:
            if parent.pk in visited or parent.archived or parent.state_code in ("COMPLETADA", "CANCELADA"):
                raise ValidationError({"state_code": "Reabre primero las tareas padre"})
            visited.add(parent.pk)
            parent = parent.parent
    if target in ("EN_CURSO", "EN_REVISION", "COMPLETADA") and TaskDependency.objects.filter(successor=task).exclude(predecessor__state_code="COMPLETADA", predecessor__archived=False).exists():
        raise ValidationError({"state_code": "Hay dependencias pendientes"})
    if task.state_code == "COMPLETADA" and TaskDependency.objects.filter(predecessor=task, successor__archived=False).exclude(successor__state_code__in=("PENDIENTE", "CANCELADA")).exists():
        raise ValidationError({"state_code": "Replanifica primero las tareas sucesoras"})
    descendants = list(Task.objects.filter(project=project, archived=False).values("id", "parent_id", "state_code"))
    pending = [task.pk]
    visited = set()
    incompatible = {"COMPLETADA", "CANCELADA"} if target == "COMPLETADA" else {"CANCELADA"}
    while pending and target in ("COMPLETADA", "CANCELADA"):
        parent_id = pending.pop()
        if parent_id in visited:
            raise ValidationError({"state_code": "La jerarquía contiene un ciclo"})
        visited.add(parent_id)
        for child in descendants:
            if child["parent_id"] == parent_id:
                if child["state_code"] not in incompatible:
                    raise ValidationError({"state_code": "Hay subtareas incompatibles con el cierre"})
                pending.append(child["id"])


def change_task_state(user, project_id, task_id, data):
    if connection.vendor == "mysql":
        project = project_for_user(user, project_id)
        task = task_for_user(user, project, task_id)
        require_task_permission(user, project, task, "worker_state")
        validate_transition(user, project, task, data["state_code"], data["reason"])
        with audit_actor(user), connection.cursor() as cursor:
            cursor.callproc("sp_cambiar_estado_actividad", [project.pk, task.pk, data["state_code"], data["reason"] or None])
            while cursor.nextset():
                pass
        task.refresh_from_db()
        return task
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        task = task_for_user(user, project, task_id)
        require_task_permission(user, project, task, "worker_state")
        validate_transition(user, project, task, data["state_code"], data["reason"])
        origin = task.state_code
        task.state_code = data["state_code"]
        task.reason = data["reason"] or None
        if task.state_code == "COMPLETADA":
            task.progress = 100
        elif task.state_code in ("PENDIENTE", "CANCELADA") or origin in ("COMPLETADA", "CANCELADA"):
            task.progress = 0
        task.updated_at = timezone.now()
        task.save()
    return task


def dependency_would_cycle(edges, predecessor, successor):
    neighbors = {}
    for source, target in edges:
        neighbors.setdefault(source, []).append(target)
    visited = set()
    pending = [successor]
    while pending:
        node = pending.pop()
        if node == predecessor:
            return True
        if node not in visited:
            visited.add(node)
            pending.extend(neighbors.get(node, []))
    return False


def manage_dependency(user, project_id, task_id, predecessor_id, remove=False):
    require_admin(user)
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        editable_project(project)
        successor = task_for_user(user, project, task_id)
        predecessor = task_for_user(user, project, predecessor_id)
        if successor.pk == predecessor.pk or successor.parent_id or predecessor.parent_id:
            raise ValidationError({"detail": "Usa dos tareas principales diferentes del mismo proyecto"})
        queryset = TaskDependency.objects.filter(project=project, predecessor=predecessor, successor=successor)
        if remove:
            if not queryset.exists():
                raise NotFound("Dependencia no disponible")
            queryset.delete()
        else:
            if queryset.exists():
                raise ValidationError({"detail": "La dependencia ya existe"})
            edges = TaskDependency.objects.filter(project=project).values_list("predecessor_id", "successor_id")
            if dependency_would_cycle(edges, predecessor.pk, successor.pk):
                raise ValidationError({"detail": "La dependencia generaría un ciclo"})
            TaskDependency.objects.create(project=project, predecessor=predecessor, successor=successor)
