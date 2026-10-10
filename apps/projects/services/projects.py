from uuid import uuid4

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.authentication.models import User
from apps.organization.models import Area
from apps.organization.services.areas import active_area_ids
from apps.workers.models import Worker
from apps.workers.services.access import eligible_workers

from ..models import Project, ProjectArea, ProjectMember, ProjectRequirement, ProjectState, ProjectTaskStatus, ProjectType
from .access import can_create_tasks, require_admin
from .audit import audit_actor
from .statuses import status_configuration


def project_areas(project):
    ids = ProjectArea.objects.filter(project=project).values_list("area_id", flat=True)
    if ids.exists():
        return Area.objects.filter(pk__in=ids)
    return Area.objects.filter(pk=project.area_id)


def eligible_project_workers(project):
    areas = list(project_areas(project).filter(active=True).values_list("pk", flat=True))
    return eligible_workers(areas) if areas else Worker.objects.none()


def project_snapshot(project, user, detailed=False):
    admin = user.global_role == "ADMINISTRADOR"
    result = {
        "id": project.pk,
        "name": project.name,
        "description": project.description or "",
        "start_date": project.start_date,
        "end_date": project.end_date,
        "state_code": project.state_code,
        "available": project.available,
        "areas": list(project_areas(project).values("id", "name")),
        "worker_edit": project.worker_edit,
        "worker_state": project.worker_state,
        "worker_create": project.worker_create,
        "permissions": {
            "manage": admin and project.state_code not in ("FINALIZADO", "CANCELADO"),
            "create_tasks": can_create_tasks(user, project),
        },
    }
    if detailed:
        members = ProjectMember.objects.filter(project=project, active=True, worker__in=eligible_project_workers(project))
        if not admin:
            members = members.filter(worker_id=user.worker_id)
        result["participants"] = [
            {"id": member.worker_id, "name": f"{member.worker.first_names} {member.worker.last_names}"}
            for member in members.select_related("worker")
        ]
        result["requirements"] = list(ProjectRequirement.objects.filter(project=project).values("id", "name", "kind"))
        result["task_states"] = status_configuration(project, user)
    return result


def create_project(user, data):
    require_admin(user)
    with audit_actor(user), transaction.atomic():
        ProjectTaskStatus.objects.exists()
        start_date = timezone.localdate()
        if data["end_date"] < start_date:
            raise ValidationError({"end_date": "La fecha final no puede ser anterior al inicio"})
        list(Area.objects.select_for_update().filter(pk__in=data["area_ids"]).order_by("pk"))
        areas = active_area_ids(data["area_ids"])
        list(Worker.objects.select_for_update().filter(pk__in=data["worker_ids"]).order_by("pk"))
        list(User.objects.select_for_update().filter(worker_id__in=data["worker_ids"]).order_by("pk"))
        workers = list(eligible_workers(areas).filter(pk__in=data["worker_ids"]))
        if len(workers) != len(data["worker_ids"]):
            raise ValidationError({"worker_ids": "Hay trabajadores no elegibles para las áreas seleccionadas"})
        if (
            not ProjectType.objects.filter(pk="GENERAL").exists()
            or not ProjectState.objects.filter(pk="PLANIFICADO", terminal=False).exists()
        ):
            raise ValidationError(
                {"detail": "El catálogo necesario no está disponible. Revisa las migraciones pendientes"}
            )
        project = Project.objects.create(
            code=f"GM-{uuid4().hex}",
            name=data["name"],
            description=data["description"],
            area_id=data["area_ids"][0],
            type_code="GENERAL",
            start_date=start_date,
            end_date=data["end_date"],
            available=data["mode"] == "available",
            worker_edit=False,
            worker_create=data["worker_contribute"],
            worker_state=data["worker_contribute"],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        ProjectArea.objects.bulk_create([ProjectArea(project=project, area_id=area_id) for area_id in areas])
        ProjectMember.objects.bulk_create([ProjectMember(project=project, worker=worker) for worker in workers])
    return project


def worker_candidates(area_ids, search):
    workers = eligible_workers(area_ids, search).order_by("last_names", "first_names")[:100]
    result = []
    for worker in workers:
        related = ProjectMember.objects.filter(worker=worker, active=True, project__archived=False).aggregate(
            total=Count("project_id", distinct=True)
        )["total"]
        result.append({"id": worker.pk, "name": f"{worker.first_names} {worker.last_names}", "project_count": related})
    return result
