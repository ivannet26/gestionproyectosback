from django.db.models import Exists, OuterRef, Q
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.authentication.services.eligibility import account_eligible
from apps.workers.services.areas import authorized_areas
from ..models import Project, ProjectArea, ProjectMember, Task


def require_admin(user):
    if user.global_role != "ADMINISTRADOR":
        raise PermissionDenied("Esta operación requiere Administrador")


def can_access_project(user, area_id, *, is_member, is_assigned):
    if not account_eligible(user):
        return False
    if user.global_role == "ADMINISTRADOR":
        return True
    return bool(is_member and is_assigned and authorized_areas(user.worker).filter(pk=area_id).exists())


def can_supervise_project(user, area_id, *, is_member, project_role):
    if not account_eligible(user):
        return False
    if user.global_role == "ADMINISTRADOR":
        return True
    return bool(
        is_member
        and project_role in ("RESPONSABLE", "REVISOR")
        and authorized_areas(user.worker).filter(pk=area_id).exists()
    )


def visible_projects(user):
    projects = Project.objects.filter(archived=False)
    if user.global_role == "ADMINISTRADOR":
        return projects
    if user.global_role != "TRABAJADOR":
        raise PermissionDenied("Cuenta no autorizada")
    areas = authorized_areas(user.worker).values_list("pk", flat=True)
    relationships = ProjectArea.objects.filter(project_id=OuterRef("pk"))
    members = ProjectMember.objects.filter(project_id=OuterRef("pk"), worker_id=user.worker_id)
    return (
        projects.annotate(
            has_areas=Exists(relationships),
            matches_area=Exists(relationships.filter(area_id__in=areas)),
            is_member=Exists(members.filter(active=True)),
            revoked_member=Exists(members.filter(active=False)),
        )
        .filter(Q(matches_area=True) | Q(has_areas=False, area_id__in=areas))
        .filter(Q(is_member=True) | Q(available=True, confidential=False, revoked_member=False))
    )


def project_for_user(user, project_id, lock=False):
    queryset = visible_projects(user)
    if lock:
        queryset = queryset.select_for_update()
    project = queryset.filter(pk=project_id).first()
    if project is None:
        raise NotFound("Proyecto no disponible")
    return project


def tasks_for_user(user, project):
    tasks = Task.objects.filter(project=project, archived=False)
    if user.global_role == "ADMINISTRADOR":
        return tasks
    return tasks.filter(responsible_id=user.worker_id)


def task_for_user(user, project, task_id):
    task = tasks_for_user(user, project).filter(pk=task_id).first()
    if task is None:
        raise NotFound("Tarea no disponible")
    return task


def require_task_permission(user, project, task, permission):
    if user.global_role == "ADMINISTRADOR":
        return
    if user.global_role != "TRABAJADOR" or task.responsible_id != user.worker_id or not getattr(project, permission):
        raise PermissionDenied("No tienes permiso para modificar esta tarea")
    if not ProjectMember.objects.filter(project=project, worker_id=user.worker_id, active=True).exists():
        raise PermissionDenied("Se requiere participación activa en el proyecto")


def can_create_tasks(user, project):
    if project.state_code in ("FINALIZADO", "CANCELADO"):
        return False
    if user.global_role == "ADMINISTRADOR":
        return True
    return bool(
        user.global_role == "TRABAJADOR"
        and project.worker_create
        and ProjectMember.objects.filter(
            project=project,
            worker_id=user.worker_id,
            active=True,
            worker__active=True,
        ).exists()
    )


def require_task_creation(user, project):
    if not can_create_tasks(user, project):
        raise PermissionDenied("Se requiere permiso de creación y participación activa en el proyecto")
