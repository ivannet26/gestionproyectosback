from ..models import ProjectFavorite
from .access import project_for_user


def set_project_favorite(user, project_id, favorite):
    project = project_for_user(user, project_id)
    if favorite:
        ProjectFavorite.objects.get_or_create(user=user, project=project)
    else:
        ProjectFavorite.objects.filter(user=user, project=project).delete()
    return {"is_favorite": favorite}
