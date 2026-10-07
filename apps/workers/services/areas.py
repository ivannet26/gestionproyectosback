from apps.organization.models import Area

from ..models import WorkerArea


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
