from django.db.models import Exists, OuterRef, Q

from apps.pagination import cursor_page
from ..models import ProjectMember
from .access import visible_projects
from .projects import project_snapshots


def project_page(user, query):
    members = ProjectMember.objects.filter(project_id=OuterRef("pk"), active=True)
    projects = visible_projects(user).select_related("area").annotate(has_associated_workers=Exists(members))
    for word in query["search"].split():
        projects = projects.filter(Q(name__icontains=word) | Q(code__icontains=word) | Q(area__name__icontains=word))
    for field in ("area_id", "state_code", "available"):
        if field in query:
            projects = projects.filter(**{field: query[field]})
    if "associated" in query:
        projects = projects.filter(has_associated_workers=query["associated"])
    return cursor_page(
        projects, query=query, user=user, resource="projects",
        serialize=lambda rows: project_snapshots(rows, user),
    )
