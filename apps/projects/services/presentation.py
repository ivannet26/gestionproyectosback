from collections import defaultdict
from django.db.models import Q

from ..models import ProjectMember, TaskAssignee, TaskDependency, TaskLabel, TaskTransition
from .statuses import configured_states
from .state_categories import definition_rules, transition_policy


def task_snapshots(tasks, project, user):
    tasks = list(tasks)
    if not tasks:
        return []
    admin = user.global_role == "ADMINISTRADOR"
    terminal = project.state_code in ("FINALIZADO", "CANCELADO")
    manageable = admin and not terminal
    membership = (
        None
        if admin
        else (
            ProjectMember.objects.filter(project=project, worker_id=user.worker_id, active=True)
            .values("project_role", "worker__active")
            .first()
        )
    )
    member = membership is not None
    supervision = admin or (member and membership["project_role"] in ("RESPONSABLE", "REVISOR"))
    can_create = not terminal and (
        admin
        or (user.global_role == "TRABAJADOR" and project.worker_create and member and membership["worker__active"])
    )
    definitions = configured_states(project)
    states = {state["code"]: state["name"] for state in definitions}
    metadata = {state["code"]: state for state in definitions}
    rules = definition_rules(project)
    sources = {task.state_code for task in tasks}
    transitions = TaskTransition.objects.filter(
        source__in=sources | {rules[code] for code in sources if code in rules},
        target__in=set(states) | set(rules.values()),
    )
    legacy = {(item["source"], item["target"]): item for item in transitions.values(
        "source", "target", "reason_required", "supervision_required",
    )}
    transitions_by_state = defaultdict(list)
    for source in {task.state_code for task in tasks}:
        for target in states:
            policy = transition_policy(source, target, rules, legacy)
            if policy and (supervision or not policy["supervision_required"]):
                transitions_by_state[source].append({"target": target, "reason_required": policy["reason_required"]})
    labels = defaultdict(list)
    assignees = defaultdict(dict)
    for task in tasks:
        if task.responsible_id is not None:
            assignees[task.pk][task.responsible_id] = {
                "id": task.responsible_id,
                "name": f"{task.responsible.first_names} {task.responsible.last_names}",
            }
    for assignment in TaskAssignee.objects.filter(task__in=tasks).select_related("worker"):
        assignees[assignment.task_id][assignment.worker_id] = {
            "id": assignment.worker_id,
            "name": f"{assignment.worker.first_names} {assignment.worker.last_names}",
        }
    for label in TaskLabel.objects.filter(task__in=tasks).values("task_id", "id", "requirement_id", "name", "kind"):
        labels[label.pop("task_id")].append(label)
    dependencies = TaskDependency.objects.filter(successor__in=tasks)
    if not admin:
        dependencies = dependencies.filter(
            Q(predecessor__responsible_id=user.worker_id)
            | Q(predecessor_id__in=TaskAssignee.objects.filter(worker_id=user.worker_id).values("task_id"))
        )
    dependencies_by_task = defaultdict(list)
    for successor_id, predecessor_id in dependencies.values_list("successor_id", "predecessor_id"):
        dependencies_by_task[successor_id].append(predecessor_id)
    return [
        task_snapshot_from_context(
            task, user, states, labels[task.pk], dependencies_by_task[task.pk],
            transitions_by_state[task.state_code], admin=admin, terminal=terminal, manageable=manageable,
            member=member, worker_edit=project.worker_edit, worker_state=project.worker_state, can_create=can_create,
            assignees=list(sorted(assignees[task.pk].values(), key=lambda worker: worker["id"])),
            metadata=metadata.get(task.state_code, {}),
        )
        for task in tasks
    ]


def task_snapshot_from_context(
    task, user, states, labels, dependencies, transitions, *, admin, terminal, manageable,
    member, worker_edit, worker_state, can_create, assignees, metadata,
):
    assigned = any(worker["id"] == user.worker_id for worker in assignees)
    can_edit = not terminal and (admin or (assigned and member and worker_edit))
    can_state = not terminal and (admin or (assigned and member and worker_state))
    return {
        "id": task.pk,
        "parent_id": task.parent_id,
        "name": task.name,
        "description": task.description or "",
        "state_code": task.state_code,
        "state_name": states.get(task.state_code, task.state_code),
        "state_category": metadata.get("category"),
        "state_color": metadata.get("color"),
        "priority": task.priority,
        "created_at": task.created_at,
        "start_date": task.start_date,
        "due_date": task.due_date,
        "estimated_minutes": task.estimated_minutes,
        "responsible_id": task.responsible_id,
        "responsible_name": f"{task.responsible.first_names} {task.responsible.last_names}"
        if task.responsible_id
        else None,
        "labels": labels,
        "assignees": assignees,
        "dependencies": dependencies,
        "transitions": transitions if can_state else [],
        "permissions": {
            "edit": can_edit,
            "state": can_state,
            "assign": manageable,
            "create_child": can_create and (admin or assigned) and metadata.get("category") not in ("done", "closed"),
            "dependencies": manageable and not task.parent_id,
            "relations": manageable,
        },
    }


def task_snapshot(task, project, user):
    return task_snapshots([task], project, user)[0]
