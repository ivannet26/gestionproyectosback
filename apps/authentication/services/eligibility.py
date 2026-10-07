from apps.workers.services.areas import authorized_areas

from ..models import FINAL_ROLES


def account_eligible(user):
    if (
        not user.is_active
        or not user.worker.active
        or not user.worker.email
        or user.global_role not in FINAL_ROLES
    ):
        return False
    return user.global_role == "ADMINISTRADOR" or authorized_areas(user.worker).exists()
