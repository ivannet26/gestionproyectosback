from django.db.models import Count, Exists, OuterRef, Q

from apps.authentication.models import FINAL_ROLES
from apps.organization.services.areas import active_area_ids
from ..models import Worker, WorkerArea


def eligible_workers(area_ids, search=""):
    areas = active_area_ids(area_ids)
    relationships = WorkerArea.objects.filter(worker_id=OuterRef("pk"))
    workers = Worker.objects.filter(active=True, user__is_active=True).annotate(
        has_areas=Exists(relationships),
        matches_area=Exists(relationships.filter(area_id__in=areas)),
        role_count=Count("user__userrole"),
        allowed_roles=Count(
            "user__userrole", filter=Q(user__userrole__role_code__in=FINAL_ROLES)
        ),
    ).filter(role_count=1, allowed_roles=1).filter(
        Q(all_areas=True) | Q(matches_area=True) | Q(has_areas=False, area_id__in=areas)
    )
    for word in search.split():
        workers = workers.filter(
            Q(first_names__icontains=word) | Q(last_names__icontains=word)
        )
    return workers
