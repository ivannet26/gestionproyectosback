from ..models import TaskStateDefinition


CATEGORIES = ("not_started", "active", "done", "closed")
LEGACY_CATEGORIES = {"PENDIENTE": "not_started", "COMPLETADA": "closed", "CANCELADA": "closed"}
COLORS = {"not_started": "#737373", "active": "#2563eb", "done": "#0d9488", "closed": "#26834a"}
LEGACY_COLORS = {
    "PENDIENTE": "#46545a", "EN_CURSO": "#1678bd", "COMPLETADA": "#248054",
    "CANCELADA": "#a42a28", "BLOQUEADA": "#a42a28", "EN_REVISION": "#6b3899", "OBSERVADA": "#6b3899",
}


def definition_rules(project):
    return {
        item["code"]: "PENDIENTE" if item["category"] == "not_started" else
        "COMPLETADA" if item["category"] in ("done", "closed") else "EN_CURSO"
        for item in TaskStateDefinition.objects.filter(project=project).values("code", "category")
    }


def state_rule(project, code):
    return definition_rules(project).get(code, code)


def transition_policy(source, target, rules, legacy):
    if source == target:
        return None
    return {"supervision_required": False, "reason_required": False}
