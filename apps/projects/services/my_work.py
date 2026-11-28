from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import reduce
from operator import or_

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.pagination import cursor_page

from ..models import ProjectTaskStatus, Task, TaskAssignee
from .access import visible_projects
from .state_categories import CATEGORIES
from .statuses import catalog_states

PRIORITY_NAMES = {1: "Urgente", 2: "Alta", 3: "Normal", 4: "Baja"}
FINISHED_CATEGORIES = ("done", "closed")
RECENT_LIMIT = 5

# Cache simple de state_index por sesión para evitar consultas repetidas a ProjectTaskStatus
_cached_state_index = {}


def visible_project_ids(user):
    return list(visible_projects(user).values_list("pk", flat=True))


def assigned_tasks(user):
    additional = TaskAssignee.objects.filter(task_id=OuterRef("pk"), worker_id=user.worker_id)
    return (
        Task.objects.filter(project_id__in=visible_project_ids(user), archived=False)
        .annotate(is_additional_assignee=Exists(additional))
        .filter(Q(responsible_id=user.worker_id) | Q(is_additional_assignee=True))
    )


def detailed(tasks):
    return tasks.select_related("project", "responsible").defer("description", "reason")


def state_index(project_ids):
    key = tuple(sorted(project_ids))
    if key in _cached_state_index:
        return _cached_state_index[key]
    configured = defaultdict(dict)
    rows = ProjectTaskStatus.objects.filter(project_id__in=project_ids).values(
        "project_id", "code", "name", "category"
    )
    for row in rows:
        configured[row["project_id"]][row["code"]] = {"name": row["name"], "category": row["category"]}
    fallback = {state["code"]: {"name": state["name"], "category": state["category"]} for state in catalog_states()}
    _cached_state_index[key] = (configured, fallback)
    return configured, fallback


def state_entry(index, project_id, code):
    configured, fallback = index
    return configured.get(project_id, fallback).get(code) or {"name": code, "category": None}


def finished(entry):
    return entry["category"] in FINISHED_CATEGORIES


def category_clauses(index, project_ids, categories):
    configured, fallback = index
    clauses = []
    for project_id in project_ids:
        states = configured.get(project_id, fallback)
        codes = [code for code, state in states.items() if state["category"] in categories]
        if codes:
            clauses.append(Q(project_id=project_id, state_code__in=codes))
    return clauses


def only_categories(tasks, index, project_ids, categories):
    clauses = category_clauses(index, project_ids, categories)
    return tasks.filter(reduce(or_, clauses)) if clauses else tasks.none()


def without_finished(tasks, index, project_ids):
    clauses = category_clauses(index, project_ids, FINISHED_CATEGORIES)
    return tasks.exclude(reduce(or_, clauses)) if clauses else tasks


def task_item(task, index, today):
    entry = state_entry(index, task.project_id, task.state_code)
    due = task.due_date
    return {
        "id": task.pk,
        "name": task.name,
        "project_id": task.project_id,
        "project_name": task.project.name,
        "state_code": task.state_code,
        "state_name": entry["name"],
        "state_category": entry["category"],
        "priority": task.priority,
        "priority_name": PRIORITY_NAMES.get(task.priority, PRIORITY_NAMES[3]),
        "start_date": task.start_date,
        "due_date": due,
        "overdue": bool(due is not None and due < today and not finished(entry)),
        "progress": float(task.progress or 0),
        "responsible_id": task.responsible_id,
        "responsible_name": (
            f"{task.responsible.first_names} {task.responsible.last_names}"
            if task.responsible_id is not None and task.responsible is not None
            else None
        ),
        "updated_at": task.updated_at,
    }


def items_by_ids(tasks, ids, index, today):
    if not ids:
        return []
    found = {task.pk: task for task in detailed(tasks.filter(id__in=ids))}
    return [task_item(found[task_id], index, today) for task_id in ids if task_id in found]


def my_work_summary(user):
    today = timezone.localdate()
    week = today + timedelta(days=7)
    tasks = assigned_tasks(user)
    rows = list(tasks.values("id", "project_id", "state_code", "priority", "due_date", "updated_at"))
    index = state_index(sorted({row["project_id"] for row in rows}))
    counts = Counter({"total": len(rows), "overdue": 0, "due_today": 0, "due_week": 0})
    counts.update({category: 0 for category in CATEGORIES})
    priorities = [
        {"code": code, "name": name, "total": 0, "pending": 0} for code, name in PRIORITY_NAMES.items()
    ]
    enriched = []
    for row in rows:
        entry = state_entry(index, row["project_id"], row["state_code"])
        pending = not finished(entry)
        due = row["due_date"]
        counts[entry["category"] if entry["category"] in CATEGORIES else "not_started"] += 1
        if due is not None and pending:
            if due < today:
                counts["overdue"] += 1
            elif due == today:
                counts["due_today"] += 1
            elif due <= week:
                counts["due_week"] += 1
        priority = row["priority"] if row["priority"] in PRIORITY_NAMES else 3
        bucket = priorities[priority - 1]
        bucket["total"] += 1
        if pending:
            bucket["pending"] += 1
        enriched.append({**row, "pending": pending})
    recent_ids = [
        row["id"] for row in sorted(enriched, key=lambda row: row["updated_at"], reverse=True)[:RECENT_LIMIT]
    ]
    urgent = (row for row in enriched if row["priority"] in (1, 2) and row["pending"])
    priority_ids = [
        row["id"]
        for row in sorted(urgent, key=lambda row: (row["priority"], row["due_date"] or date.max, row["id"]))[
            :RECENT_LIMIT
        ]
    ]
    return {
        "counts": dict(counts),
        "priorities": priorities,
        "recent": items_by_ids(tasks, recent_ids, index, today),
        "priority_tasks": items_by_ids(tasks, priority_ids, index, today),
    }


def my_work_page(user, query):
    today = timezone.localdate()
    tasks = assigned_tasks(user)
    project_ids = list(tasks.values_list("project_id", flat=True).distinct())
    index = state_index(project_ids)
    categories = query.get("state_category")
    if categories:
        tasks = only_categories(tasks, index, project_ids, categories)
    due = query.get("due", "any")
    if due in ("overdue", "today", "week"):
        if not categories:
            tasks = without_finished(tasks, index, project_ids)
        if due == "overdue":
            tasks = tasks.filter(due_date__lt=today)
        elif due == "today":
            tasks = tasks.filter(due_date=today)
        else:
            tasks = tasks.filter(due_date__gt=today, due_date__lte=today + timedelta(days=7))
    elif due == "none":
        tasks = tasks.filter(due_date__isnull=True)
    if "project_id" in query:
        tasks = tasks.filter(project_id=query["project_id"])
    if "priority" in query:
        tasks = tasks.filter(priority=query["priority"])
    for word in query["search"].split():
        tasks = tasks.filter(Q(name__icontains=word) | Q(project__name__icontains=word))
    return cursor_page(
        detailed(tasks),
        query=query,
        user=user,
        resource="my-work-tasks",
        serialize=lambda rows: [task_item(task, index, today) for task in rows],
    )


def my_work_upcoming(user, days, limit):
    today = timezone.localdate()
    tasks = assigned_tasks(user)
    project_ids = list(tasks.values_list("project_id", flat=True).distinct())
    index = state_index(project_ids)
    end = today + timedelta(days=days)
    rows = detailed(tasks).filter(due_date__lte=end).order_by("due_date", "priority", "pk")
    pending = [task for task in rows if not finished(state_entry(index, task.project_id, task.state_code))]
    return {
        "range": {"start": today.isoformat(), "end": end.isoformat()},
        "overdue": [task_item(task, index, today) for task in pending if task.due_date < today][:limit],
        "upcoming": [task_item(task, index, today) for task in pending if task.due_date >= today][:limit],
    }


def my_work_priorities(user, priorities, limit):
    today = timezone.localdate()
    tasks = assigned_tasks(user)
    project_ids = list(tasks.values_list("project_id", flat=True).distinct())
    index = state_index(project_ids)
    rows = list(tasks.values("id", "project_id", "state_code", "priority", "due_date"))
    candidates = [
        row
        for row in rows
        if row["priority"] in priorities
        and not finished(state_entry(index, row["project_id"], row["state_code"]))
    ]
    candidates.sort(key=lambda row: (row["priority"], row["due_date"] or date.max, row["id"]))
    return {"tasks": items_by_ids(tasks, [row["id"] for row in candidates[:limit]], index, today)}
