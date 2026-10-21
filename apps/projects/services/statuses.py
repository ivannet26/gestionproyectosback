import hashlib
import json
import uuid

from django.db import connection, transaction
from django.db.models import Count
from rest_framework.exceptions import ValidationError

from ..models import ProjectTaskStatus, Task, TaskState, TaskStateDefinition, TaskTransition
from .access import project_for_user, require_admin
from .audit import audit_actor
from .state_categories import CATEGORIES, COLORS, LEGACY_CATEGORIES, LEGACY_COLORS
from .state_categories import state_rule


STANDARD_NAMES = {"PENDIENTE": "PENDIENTE", "EN_CURSO": "EN CURSO", "COMPLETADA": "CERRADO"}
STANDARD_ORDER = {code: position for position, code in enumerate(STANDARD_NAMES)}


def catalog_states():
    states = []
    for item in TaskState.objects.exclude(code__in=TaskStateDefinition.objects.values("code")).values("code", "name", "terminal"):
        category = LEGACY_CATEGORIES.get(item["code"], "closed" if item["terminal"] else "active")
        states.append({"code": item["code"], "name": STANDARD_NAMES.get(item["code"], item["name"]),
                       "category": category, "color": LEGACY_COLORS.get(item["code"], COLORS[category])})
    return sorted(states, key=lambda state: (STANDARD_ORDER.get(state["code"], 3), state["code"]))


def configured_states(project):
    return list(ProjectTaskStatus.objects.filter(project=project).values("code", "name", "category", "color")) or catalog_states()


def status_configuration(project, user):
    saved = list(ProjectTaskStatus.objects.filter(project=project).values("code", "name", "category", "color"))
    catalog = catalog_states()
    states = saved or catalog
    template = "custom" if saved else "standard"
    revision = hashlib.sha256(json.dumps([template, states], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    admin = user.global_role == "ADMINISTRADOR"
    usage = dict(Task.objects.filter(project=project).values("state_code").annotate(total=Count("id"))
                 .values_list("state_code", "total")) if admin else {}
    return {"template": template, "states": states, "available_states": catalog, "revision": revision,
            "usage": usage, "can_configure": admin and project.state_code not in ("FINALIZADO", "CANCELADO")}


def require_configured_state(project, code):
    if code not in {state["code"] for state in configured_states(project)}:
        raise ValidationError({"state_code": "El estado no está habilitado en este proyecto"})
    if not TaskState.objects.filter(code=code).exists():
        raise ValidationError({"state_code": "El estado no existe"})


def validate_status_configuration(project, states):
    codes = {state["code"] for state in states}
    if not set(STANDARD_NAMES) <= codes:
        raise ValidationError({"states": "Conserva Pendiente, En curso y Cerrado"})
    transitions = list(TaskTransition.objects.values_list("source", "target"))
    reachable = {"PENDIENTE"}
    while True:
        expanded = reachable | {target for source, target in transitions if source in reachable and target in codes}
        if expanded == reachable:
            break
        reachable = expanded
    if not {"EN_CURSO", "COMPLETADA"} <= reachable:
        raise ValidationError({"states": "Conserva los estados intermedios de las transiciones vigentes"})


def resolve_states(project, requested):
    available = {state["code"]: state for state in configured_states(project) + catalog_states()}
    owned = set(TaskStateDefinition.objects.filter(project=project).values_list("code", flat=True))
    has_custom = False
    resolved = []
    identities = {}
    new_states = []
    new_definitions = []
    for item in requested:
        code = item["code"]
        existing = available.get(code)
        if existing:
            category = item.get("category", existing["category"])
            if category != existing["category"]:
                raise ValidationError({"states": "La categoría de un estado existente no se puede cambiar"})
        elif code.startswith("draft_"):
            category = item.get("category")
        else:
            raise ValidationError({"states": "El estado no pertenece al catálogo ni a este proyecto"})
        if category not in CATEGORIES:
            raise ValidationError({"states": "Indica la categoría funcional de cada estado"})
        actual = "S_" + uuid.uuid4().hex[:18] if existing is None else code
        has_custom = has_custom or code in owned
        identities[code] = actual
        if actual != code:
            new_states.append(TaskState(code=actual, name=actual, terminal=category in ("done", "closed")))
            new_definitions.append(TaskStateDefinition(code=actual, project=project, category=category))
            has_custom = True
        resolved.append({"code": actual, "name": item["name"], "category": category,
                         "color": item.get("color", existing["color"] if existing else COLORS[category])})
    categories = {item["category"] for item in resolved}
    if not {"not_started", "active", "closed"} <= categories:
        raise ValidationError({"states": "El flujo necesita al menos un estado No iniciado, Activo y Cerrado"})
    if not has_custom:
        validate_status_configuration(project, resolved)
    TaskState.objects.bulk_create(new_states)
    TaskStateDefinition.objects.bulk_create(new_definitions)
    return resolved, identities


def reassign_tasks(user, project, removed, identities, assignments, previous_states=None):
    from .tasks import apply_state_change, validate_transition
    from .activity import activity_values, record_state_change

    destinations = {item["source"]: item for item in assignments}
    used = set(Task.objects.filter(project=project, state_code__in=removed).values_list("state_code", flat=True))
    if used - destinations.keys():
        raise ValidationError({"reassignments": "Elige un destino para cada estado con tareas o subtareas"})
    for source, item in destinations.items():
        if source not in removed or item["target"] not in identities:
            raise ValidationError({"reassignments": "Selecciona orígenes retirados y destinos del nuevo flujo"})
    pending = {task.pk: task for task in Task.objects.filter(project=project, state_code__in=removed)}
    while pending:
        previous_count = len(pending)
        failure = None
        for task in list(pending.values()):
            item = destinations[task.state_code]
            target = identities[item["target"]]
            try:
                with transaction.atomic():
                    task.refresh_from_db()
                    if task.archived:
                        if state_rule(project, task.state_code) != state_rule(project, target):
                            raise ValidationError({"reassignments": "Para tareas archivadas elige un destino de la misma fase funcional"})
                        before = activity_values(task)
                        if previous_states:
                            before["state_code"] = next((state for state in previous_states if state["code"] == task.state_code), before["state_code"])
                        task.state_code = target
                        task.save(update_fields=["state_code"])
                        record_state_change(task, before)
                    else:
                        validate_transition(user, project, task, target, item["reason"])
                        before = activity_values(task)
                        if previous_states:
                            before["state_code"] = next((state for state in previous_states if state["code"] == task.state_code), before["state_code"])
                        apply_state_change(project, task, target, item["reason"], nested=True, before=before)
            except ValidationError as error:
                failure = error
            else:
                del pending[task.pk]
        if len(pending) == previous_count:
            raise failure


def configure_task_states(user, project_id, data):
    require_admin(user)
    with audit_actor(user), transaction.atomic():
        project = project_for_user(user, project_id, lock=True)
        if project.state_code in ("FINALIZADO", "CANCELADO"):
            raise ValidationError({"detail": "No se puede configurar un proyecto cerrado"})
        previous = status_configuration(project, user)
        if data["revision"] != previous["revision"]:
            raise ValidationError({"revision": "La configuración cambió. Vuelve a cargarla antes de guardar"})
        requested = data["states"] if data["template"] == "custom" else catalog_states()
        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("SET @gm_estados_anteriores = %s", [json.dumps({state["code"]: state for state in previous["states"]})])
        states, identities = resolve_states(project, requested)
        removed = ({state["code"] for state in previous["states"]} | set(previous["usage"])) - set(identities.values())
        ProjectTaskStatus.objects.filter(project=project).delete()
        ProjectTaskStatus.objects.bulk_create([
            ProjectTaskStatus(project=project, position=position, **state) for position, state in enumerate(states)
        ])
        reassign_tasks(user, project, removed, identities, data.get("reassignments", []), previous["states"])
        if data["template"] == "standard":
            ProjectTaskStatus.objects.filter(project=project).delete()
        return status_configuration(project, user)
