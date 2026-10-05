from ..models import Area, FINAL_ROLES, WorkerArea


def authorized_areas(worker):
    areas = Area.objects.filter(active=True)
    if worker.all_areas:
        return areas
    selected = WorkerArea.objects.filter(worker=worker).values_list("area_id", flat=True)
    if selected.exists():
        return areas.filter(pk__in=selected)
    return areas.filter(pk=worker.area_id)


def area_summary(worker):
    return {
        "all_areas": worker.all_areas,
        "areas": list(authorized_areas(worker).order_by("name").values("id", "name")),
    }


def account_eligible(user):
    if not user.is_active or not user.worker.active or not user.worker.email or user.global_role not in FINAL_ROLES:
        return False
    return user.global_role == "ADMINISTRADOR" or authorized_areas(user.worker).exists()


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
    return bool(is_member and project_role in ("RESPONSABLE", "REVISOR") and authorized_areas(user.worker).filter(pk=area_id).exists())
