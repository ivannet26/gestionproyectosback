import unittest
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authentication.tokens import issue_access
from apps.projects.models import Task, Tema

from . import test_projects as fixtures


class MyWorkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProjectFlowTests.setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(Tema)
        fixtures.ProjectFlowTests.tables.append(Tema)

    @classmethod
    def tearDownClass(cls):
        fixtures.ProjectFlowTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.ProjectFlowTests()
        self.fixture.setUp()
        self.worker = self.fixture.worker
        self.admin = self.fixture.admin
        self.project = self.fixture.assigned_project()
        self.hidden_project = self.fixture.project()
        self.today = self.fixture.today

    def tearDown(self):
        self.fixture.tearDown()

    def get(self, path="", user=None):
        headers = {}
        if user is not None:
            if user.pk not in self.fixture.tokens:
                self.fixture.tokens[user.pk] = issue_access(user, timezone.now() + timedelta(hours=1))
            headers["HTTP_AUTHORIZATION"] = f"Bearer {self.fixture.tokens[user.pk]}"
        return self.fixture.client.get(f"/api/my-work/{path}", content_type="application/json", **headers)

    def task(self, **changes):
        return self.fixture.task(self.project, **changes)

    def shift_due(self, task, days):
        Task.objects.filter(pk=task.pk).update(due_date=self.today + timedelta(days=days))
        task.refresh_from_db()
        return task

    def hidden_task(self, **changes):
        task = Task.objects.create(
            project=self.hidden_project,
            name="Tarea fuera de alcance",
            state_code="PENDIENTE",
            priority=2,
            start_date=self.today,
            due_date=self.today + timedelta(days=1),
            responsible_id=self.worker.worker_id,
            **changes,
        )
        return task

    def test_endpoints_require_authentication(self):
        for path in ("summary/", "tasks/", "upcoming/", "priorities/"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 401)

    def test_summary_counts_only_my_visible_assigned_tasks(self):
        mine = self.task(responsible_id=self.worker.worker_id, priority=1)
        self.shift_due(mine, -2)
        self.task()
        closed = self.task(responsible_id=self.worker.worker_id, state_code="COMPLETADA")
        hidden = self.hidden_task()
        summary = self.get("summary/", self.worker).json()
        counts = summary["counts"]
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["not_started"], 1)
        self.assertEqual(counts["closed"], 1)
        self.assertEqual(counts["overdue"], 1)
        self.assertEqual(counts["due_today"], 0)
        self.assertEqual(counts["due_week"], 0)
        self.assertEqual([item["id"] for item in summary["recent"]], [closed.pk, mine.pk])
        self.assertEqual([item["id"] for item in summary["priority_tasks"]], [mine.pk])
        self.assertEqual(
            summary["priorities"][0], {"code": 1, "name": "Urgente", "total": 1, "pending": 1}
        )
        self.assertEqual(
            summary["priorities"][2], {"code": 3, "name": "Normal", "total": 1, "pending": 0}
        )
        overdue_item = summary["priority_tasks"][0]
        self.assertEqual(overdue_item["project_id"], self.project.pk)
        self.assertEqual(overdue_item["state_category"], "not_started")
        self.assertEqual(overdue_item["priority_name"], "Urgente")
        self.assertTrue(overdue_item["overdue"])
        self.assertEqual(overdue_item["responsible_name"], "Nombre sintético worker")
        self.assertNotIn(hidden.pk, [item["id"] for item in summary["recent"]])
        self.assertEqual(self.get("summary/", self.admin).json()["counts"]["total"], 0)

    def test_tasks_endpoint_filters_searches_and_paginates(self):
        urgent = self.task(responsible_id=self.worker.worker_id, priority=1)
        self.shift_due(urgent, -1)
        without_date = self.task(responsible_id=self.worker.worker_id, priority=3, due_date=None)
        closed = self.task(responsible_id=self.worker.worker_id, priority=2, state_code="COMPLETADA")
        mine = {urgent.pk, without_date.pk, closed.pk}

        def ids(path):
            return {item["id"] for item in self.get(path, self.worker).json()["results"]}

        self.assertEqual(ids("tasks/?priority=1"), {urgent.pk})
        self.assertEqual(ids("tasks/?due=overdue"), {urgent.pk})
        self.assertEqual(ids("tasks/?due=none"), {without_date.pk})
        self.assertEqual(ids("tasks/?state_category=closed"), {closed.pk})
        self.assertEqual(ids("tasks/?state_category=not_started,active"), {urgent.pk, without_date.pk})
        self.assertEqual(ids("tasks/?search=Tarea"), mine)
        self.assertEqual(ids(f"tasks/?project_id={self.hidden_project.pk}"), set())
        self.assertEqual(self.get("tasks/?due=manana", self.worker).status_code, 400)
        self.assertEqual(self.get("tasks/?priority=9", self.worker).status_code, 400)
        self.assertEqual(self.get("tasks/?state_category=terminado", self.worker).status_code, 400)

        first = self.get("tasks/?page_size=2", self.worker).json()
        self.assertEqual(first["total"], 3)
        self.assertEqual(len(first["results"]), 2)
        self.assertIsNotNone(first["next_cursor"])
        second = self.get(f"tasks/?page_size=2&cursor={first['next_cursor']}", self.worker).json()
        self.assertEqual(len(second["results"]), 1)
        self.assertIsNone(second["next_cursor"])
        self.assertFalse({item["id"] for item in first["results"]} & {item["id"] for item in second["results"]})

    def test_upcoming_separates_overdue_from_scheduled_tasks(self):
        overdue = self.task(responsible_id=self.worker.worker_id, priority=1)
        self.shift_due(overdue, -3)
        soon = self.task(responsible_id=self.worker.worker_id)
        self.shift_due(soon, 2)
        far = self.task(responsible_id=self.worker.worker_id)
        self.shift_due(far, 40)
        closed_soon = self.task(responsible_id=self.worker.worker_id, state_code="COMPLETADA")
        self.shift_due(closed_soon, 1)

        data = self.get("upcoming/?days=14", self.worker).json()
        self.assertEqual(
            data["range"], {"start": str(self.today), "end": str(self.today + timedelta(days=14))}
        )
        self.assertEqual([item["id"] for item in data["overdue"]], [overdue.pk])
        self.assertEqual([item["id"] for item in data["upcoming"]], [soon.pk])
        self.assertEqual(self.get("upcoming/?days=0", self.worker).status_code, 400)
        self.assertEqual(self.get("upcoming/?otro=1", self.worker).status_code, 400)

    def test_priorities_order_by_urgency_and_exclude_finished(self):
        later = self.task(responsible_id=self.worker.worker_id, priority=1)
        self.shift_due(later, 5)
        sooner = self.task(responsible_id=self.worker.worker_id, priority=1)
        self.shift_due(sooner, 1)
        normal = self.task(responsible_id=self.worker.worker_id, priority=3)
        closed_high = self.task(responsible_id=self.worker.worker_id, priority=1, state_code="COMPLETADA")

        data = self.get("priorities/", self.worker).json()
        self.assertEqual([item["id"] for item in data["tasks"]], [sooner.pk, later.pk])
        self.assertEqual(
            [item["id"] for item in self.get("priorities/?priority=3", self.worker).json()["tasks"]],
            [normal.pk],
        )
        limited = self.get("priorities/?priority=1,2&limit=1", self.worker).json()
        self.assertEqual([item["id"] for item in limited["tasks"]], [sooner.pk])
        self.assertEqual(self.get("priorities/?priority=alta", self.worker).status_code, 400)
        self.assertEqual(self.get("priorities/?otro=1", self.worker).status_code, 400)
        self.assertNotIn(closed_high.pk, [item["id"] for item in data["tasks"]])

    def test_summary_query_count_does_not_grow_with_task_count(self):
        self.task(responsible_id=self.worker.worker_id, priority=1)
        self.get("summary/", self.worker)
        with CaptureQueriesContext(connection) as single:
            self.assertEqual(self.get("summary/", self.worker).status_code, 200)
        for _ in range(4):
            self.task(responsible_id=self.worker.worker_id, priority=1)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.get("summary/", self.worker).status_code, 200)
        self.assertEqual(len(single), len(many))
