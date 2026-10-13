import unittest
from datetime import timedelta

from apps.projects.models import ProjectMember, TaskLabel
from .test_performance import PerformanceRegressionTests


class TaskInlineTests(unittest.TestCase):
    tables = PerformanceRegressionTests.tables
    setUpClass = classmethod(PerformanceRegressionTests.setUpClass.__func__)
    tearDownClass = classmethod(PerformanceRegressionTests.tearDownClass.__func__)
    setUp = PerformanceRegressionTests.setUp
    tearDown = PerformanceRegressionTests.tearDown

    def make_task(self):
        project = self.fixture.assigned_project(worker_edit=True, worker_contribute=True)
        task = self.fixture.task(project, responsible_id=self.fixture.worker.worker_id)
        return project, task, f"{project.pk}/tasks/{task.pk}/"

    def test_partial_start_date_preserves_unedited_data_and_is_returned(self):
        project, task, path = self.make_task()
        TaskLabel.objects.create(task=task, name="Estructuras", kind="technical")
        created = task.created_at
        date = str(self.fixture.today + timedelta(days=2))
        response = self.fixture.request("patch", path, {"start_date": date}, self.fixture.admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["start_date"], date)
        self.assertEqual(response.json()["name"], task.name)
        self.assertEqual(len(response.json()["labels"]), 1)
        task.refresh_from_db()
        self.assertEqual(task.created_at, created)
        listed = self.fixture.request("get", f"{project.pk}/tasks/", user=self.fixture.worker)
        self.assertEqual(listed.json()[0]["start_date"], date)

    def test_invalid_dates_and_nulls_do_not_change_task(self):
        project, task, path = self.make_task()
        original = task.start_date
        for data in (
            {"start_date": None}, {"start_date": ""}, {"start_date": "2026-02-30"},
            {"start_date": str(original - timedelta(days=1))},
            {"start_date": str(task.due_date + timedelta(days=1))},
            {"due_date": None}, {"priority": None},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.fixture.request("patch", path, data, self.fixture.admin).status_code, 400)
                task.refresh_from_db()
                self.assertEqual(task.start_date, original)

    def test_parent_and_child_periods_are_preserved(self):
        project, task, path = self.make_task()
        child = self.fixture.task(project, parent_id=task.pk)
        response = self.fixture.request("patch", path, {
            "start_date": str(self.fixture.today + timedelta(days=1)),
        }, self.fixture.admin)
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date", response.json())
        self.assertEqual(self.fixture.request("patch", f"{project.pk}/tasks/{child.pk}/", {
            "due_date": str(task.due_date + timedelta(days=1)),
        }, self.fixture.admin).status_code, 400)

    def test_worker_permissions_and_revocation_are_checked_for_each_patch(self):
        project, task, path = self.make_task()
        for data in ({"start_date": str(self.fixture.today + timedelta(days=1))}, {"priority": 2}):
            self.assertEqual(self.fixture.request("patch", path, data, self.fixture.worker).status_code, 200)
        self.assertEqual(self.fixture.request("patch", path, {"responsible_id": None}, self.fixture.worker).status_code, 403)
        self.assertEqual(self.fixture.request("patch", path, {"priority": 1}, self.fixture.outsider).status_code, 404)
        project.worker_edit = False
        project.save(update_fields=["worker_edit"])
        self.assertEqual(self.fixture.request("patch", path, {"priority": 1}, self.fixture.worker).status_code, 403)
        ProjectMember.objects.filter(project=project).update(active=False)
        self.assertEqual(self.fixture.request("patch", path, {"priority": 1}, self.fixture.worker).status_code, 404)

    def test_assignment_and_priority_use_existing_rules(self):
        project, task, path = self.make_task()
        for priority in (1, 2, 3, 4):
            response = self.fixture.request("patch", path, {"priority": priority}, self.fixture.admin)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["priority"], priority)
        self.assertEqual(self.fixture.request("patch", path, {"responsible_id": self.fixture.outsider.worker_id}, self.fixture.admin).status_code, 400)
        response = self.fixture.request("patch", path, {"responsible_id": None}, self.fixture.admin)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["responsible_id"])
