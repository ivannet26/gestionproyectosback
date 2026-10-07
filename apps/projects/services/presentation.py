from ..models import ProjectMember, TaskDependency, TaskLabel, TaskTransition
from .tasks import has_supervision


def task_snapshot(task, project, user):
    admin = user.global_role == "ADMINISTRADOR"
    manageable = admin and project.state_code not in ("FINALIZADO", "CANCELADO")
    assigned = task.responsible_id == user.worker_id
    member = ProjectMember.objects.filter(project=project, worker_id=user.worker_id, active=True).exists()
    can_edit = admin or (assigned and member and project.worker_edit)
    can_state = admin or (assigned and member and project.worker_state)
    if project.state_code in ("FINALIZADO", "CANCELADO"):
        can_edit = can_state = False
    transitions = TaskTransition.objects.filter(source=task.state_code)
    if not has_supervision(user, project):
        transitions = transitions.filter(supervision_required=False)
    dependencies = TaskDependency.objects.filter(successor=task)
    if not admin:
        dependencies = dependencies.filter(predecessor__responsible_id=user.worker_id)
    return {
        "id": task.pk, "parent_id": task.parent_id, "name": task.name,
        "state_code": task.state_code, "priority": task.priority,
        "created_at": task.created_at, "due_date": task.due_date,
        "responsible_id": task.responsible_id,
        "responsible_name": f"{task.responsible.first_names} {task.responsible.last_names}" if task.responsible_id else None,
        "labels": list(TaskLabel.objects.filter(task=task).values("id", "requirement_id", "name", "kind")),
        "dependencies": list(dependencies.values_list("predecessor_id", flat=True)),
        "transitions": list(transitions.values("target", "reason_required")) if can_state else [],
        "permissions": {"edit": can_edit, "state": can_state, "assign": manageable, "create_child": manageable and task.state_code not in ("COMPLETADA", "CANCELADA"), "dependencies": manageable and not task.parent_id},
    }
