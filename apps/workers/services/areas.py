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


def area_summaries(workers):
    workers = list(workers)
    selected = {}
    for worker_id, area_id in WorkerArea.objects.filter(worker__in=workers).values_list("worker_id", "area_id"):
        selected.setdefault(worker_id, set()).add(area_id)
    area_ids = {worker.area_id for worker in workers}
    for ids in selected.values():
        area_ids.update(ids)
    areas = Area.objects.filter(active=True)
    if not any(worker.all_areas for worker in workers):
        areas = areas.filter(pk__in=area_ids)
    areas = list(areas.order_by("name").values("id", "name"))
    return {
        worker.pk: {
            "all_areas": worker.all_areas,
            "areas": [
                area for area in areas
                if worker.all_areas or area["id"] in selected.get(worker.pk, {worker.area_id})
            ],
        }
        for worker in workers
    }
