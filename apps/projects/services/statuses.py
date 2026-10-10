import hashlib
import json

from django.db import transaction
from rest_framework.exceptions import ValidationError

from ..models import ProjectTaskStatus, Task, TaskState, TaskTransition
from .access import project_for_user, require_admin
from .audit import audit_actor


STANDARD_NAMES = {"PENDIENTE": "PENDIENTE", "EN_CURSO": "EN CURSO", "COMPLETADA": "CERRADO"}
STANDARD_ORDER = {code: position for position, code in enumerate(STANDARD_NAMES)}


def catalog_states():
    states = [
        {"code": state["code"], "name": STANDARD_NAMES.get(state["code"], state["name"])}
        for state in TaskState.objects.values("code", "name")
    ]
    return sorted(states, key=lambda state: (STANDARD_ORDER.get(state["code"], 3), state["code"]))


def configured_states(project):
    return list(ProjectTaskStatus.objects.filter(project=project).values("code", "name")) or catalog_states()


def status_configuration(project, user):
    saved = list(ProjectTaskStatus.objects.filter(project=project).values("code", "name"))
    states = saved or catalog_states()
    template = "custom" if saved else "standard"
    revision = hashlib.sha256(
        json.dumps([template, states], sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "template": template,
        "states": states,
        "available_states": catalog_states(),
        "revision": revision,
        "can_configure": user.global_role == "ADMINISTRADOR"
        and project.state_code not in ("FINALIZADO", "CANCELADO"),
    }


def require_configured_state(project, code):
    if code not in {state["code"] for state in configured_states(project)}:
        raise ValidationError({"state_code": "El estado no está habilitado en este proyecto"})
    if not TaskState.objects.filter(code=code).exists():
        raise ValidationError({"state_code": "El estado no existe"})


def validate_status_configuration(project, states):
    codes = {state["code"] for state in states}
    available = set(TaskState.objects.values_list("code", flat=True))
    if not codes <= available:
        raise ValidationError({"states": "Selecciona códigos del catálogo existente"})
    if not set(STANDARD_NAMES) <= codes:
        raise ValidationError({"states": "Conserva Pendiente, En curso y Cerrado"})
    used = set(Task.objects.filter(project=project).values_list("state_code", flat=True))
    if not used <= codes:
        raise ValidationError({"states": "No puedes retirar un estado utilizado por tareas o subtareas"})
    transitions = list(TaskTransition.objects.values_list("source", "target"))
    reachable = {"PENDIENTE"}
    while True:
        expanded = reachable | {target for source, target in transitions if source in reachable and target in codes}
        if expanded == reachable:
            break
        reachable = expanded
    if not {"EN_CURSO", "COMPLETADA"} <= reachable:
        raise ValidationError({"states": "Conserva los estados intermedios de las transiciones vigentes"})


def configure_task_states(user, project_id, data):
    require_admin(user)
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        if project.state_code in ("FINALIZADO", "CANCELADO"):
            raise ValidationError({"detail": "No se puede configurar un proyecto cerrado"})
        if data["revision"] != status_configuration(project, user)["revision"]:
            raise ValidationError({"revision": "La configuración cambió. Vuelve a cargarla antes de guardar"})
        states = data["states"] if data["template"] == "custom" else catalog_states()
        validate_status_configuration(project, states)
        ProjectTaskStatus.objects.filter(project=project).delete()
        if data["template"] == "custom":
            ProjectTaskStatus.objects.bulk_create(
                [
                    ProjectTaskStatus(project=project, code=state["code"], name=state["name"], position=position)
                    for position, state in enumerate(states)
                ]
            )
        return status_configuration(project, user)
