from datetime import timedelta
from itertools import combinations
import unittest

from apps.projects.models import Task, ProjectMember
from . import test_performance as fixtures


class QuickTaskTests(unittest.TestCase):
    tables = fixtures.PerformanceRegressionTests.tables
    setUpClass = classmethod(fixtures.PerformanceRegressionTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.PerformanceRegressionTests.tearDownClass.__func__)
    setUp = fixtures.PerformanceRegressionTests.setUp
    tearDown = fixtures.PerformanceRegressionTests.tearDown

    def test_only_name_and_context_preserve_real_empty_values(self):
        project = self.fixture.project()
        response = self.fixture.request("post", f"{project.pk}/tasks/", {"name": "  Solo nombre  ", "state_code": "PENDIENTE"}, self.fixture.admin)
        self.assertEqual(response.status_code, 201, response.content)
        value = response.json()
        self.assertEqual(value["name"], "Solo nombre")
        self.assertIsNone(value["due_date"])
        self.assertIsNone(value["priority"])
        self.assertIsNone(value["responsible_id"])
        self.assertEqual(value["assignees"], [])
        self.assertEqual(value["labels"], [])
        self.assertEqual(value["start_date"], str(project.start_date))

    def test_all_optional_combinations_use_the_same_endpoint(self):
        project = self.fixture.assigned_project()
        options = {"due_date": str(self.fixture.today + timedelta(days=5)), "priority": 2,
                   "responsible_ids": [self.fixture.worker.worker_id], "labels": [{"name": "Ensayo", "kind": "technical"}]}
        for count in range(5):
            for keys in combinations(options, count):
                with self.subTest(keys=keys):
                    response = self.fixture.request("post", f"{project.pk}/tasks/", {
                        "name": "Combinación sintética", "state_code": "PENDIENTE", **{key: options[key] for key in keys},
                    }, self.fixture.admin)
                    self.assertEqual(response.status_code, 201, response.content)
                    value = response.json()
                    self.assertEqual(value["priority"], options["priority"] if "priority" in keys else None)
                    self.assertEqual(value["due_date"], options["due_date"] if "due_date" in keys else None)
                    self.assertEqual(len(value["assignees"]), int("responsible_ids" in keys))
                    self.assertEqual(len(value["labels"]), int("labels" in keys))
        self.assertEqual(Task.objects.filter(project=project).count(), 16)

    def test_partial_omission_preserves_and_explicit_null_clears(self):
        project = self.fixture.assigned_project()
        task = self.fixture.task(project, responsible_id=self.fixture.worker.worker_id)
        path = f"{project.pk}/tasks/{task.pk}/"
        unchanged = self.fixture.request("patch", path, {"name": "Otro nombre"}, self.fixture.admin)
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(unchanged.json()["priority"], task.priority)
        self.assertEqual(unchanged.json()["due_date"], str(task.due_date))
        cleared = self.fixture.request("patch", path, {"due_date": None, "priority": None, "responsible_ids": [], "labels": []}, self.fixture.admin)
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(cleared.json()["due_date"])
        self.assertIsNone(cleared.json()["priority"])
        self.assertEqual(cleared.json()["assignees"], [])

    def test_supplied_values_and_required_name_stay_validated_atomically(self):
        project = self.fixture.assigned_project()
        for data in ({"name": " "}, {"priority": 0}, {"priority": 5}, {"due_date": ""}, {"due_date": "bad"},
                     {"due_date": str(self.fixture.today - timedelta(days=1))}, {"due_date": str(self.fixture.today + timedelta(days=45))},
                     {"responsible_ids": [self.fixture.outsider.worker_id]}, {"labels": [{"name": "", "kind": "technical"}]},
                     {"state_code": "EN_CURSO"}, {"state_code": "BLOQUEADA"}):
            with self.subTest(data=data):
                response = self.fixture.request("post", f"{project.pk}/tasks/", {"name": "Tarea", "state_code": "PENDIENTE", **data}, self.fixture.admin)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertFalse(Task.objects.exists())

    def test_worker_ownership_and_revoked_permissions_are_unchanged(self):
        project = self.fixture.assigned_project(worker_contribute=True)
        payload = {"name": "Tarea propia", "state_code": "PENDIENTE"}
        response = self.fixture.request("post", f"{project.pk}/tasks/", payload, self.fixture.worker)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["responsible_id"], self.fixture.worker.worker_id)
        self.assertIsNone(response.json()["due_date"])
        self.assertEqual(self.fixture.request("post", f"{project.pk}/tasks/", {**payload, "responsible_ids": [self.fixture.outsider.worker_id]}, self.fixture.worker).status_code, 403)
        self.assertEqual(self.fixture.request("post", f"{project.pk}/tasks/", payload).status_code, 401)
        ProjectMember.objects.filter(project=project).update(active=False)
        self.assertIn(self.fixture.request("post", f"{project.pk}/tasks/", payload, self.fixture.worker).status_code, (403, 404))

    def test_undated_parent_child_and_new_bounds_remain_consistent(self):
        project = self.fixture.project()
        parent = self.fixture.task(project, due_date=None, priority=None)
        child = self.fixture.task(project, parent_id=parent.pk, due_date=None, priority=None)
        path = f"{project.pk}/tasks/{parent.pk}/"
        child_path = f"{project.pk}/tasks/{child.pk}/"
        later = str(self.fixture.today + timedelta(days=10))
        self.assertEqual(self.fixture.request("patch", child_path, {"start_date": later}, self.fixture.admin).status_code, 200)
        invalid = self.fixture.request("patch", path, {"due_date": str(self.fixture.today + timedelta(days=5))}, self.fixture.admin)
        self.assertEqual(invalid.status_code, 400, invalid.content)
        self.assertEqual(self.fixture.request("patch", path, {"due_date": later}, self.fixture.admin).status_code, 200)
        self.assertEqual(self.fixture.request("patch", child_path, {"due_date": str(self.fixture.today + timedelta(days=11))}, self.fixture.admin).status_code, 400)

    def test_effective_creation_and_state_permissions_are_independent(self):
        project = self.fixture.assigned_project(worker_edit=True, worker_state=True, worker_contribute=False)
        task = self.fixture.task(project, responsible_id=self.fixture.worker.worker_id)
        path = f"{project.pk}/tasks/"
        payload = {"name": "No basta con editar", "state_code": "PENDIENTE"}
        self.assertEqual(self.fixture.request("patch", f"{path}{task.pk}/", {"name": "Puede editar"}, self.fixture.worker).status_code, 200)
        self.assertEqual(self.fixture.request("post", path, payload, self.fixture.worker).status_code, 403)
        project.worker_create = True
        project.worker_state = False
        project.save(update_fields=["worker_create", "worker_state"])
        response = self.fixture.request("post", path, payload, self.fixture.worker)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json()["permissions"]["state"])
        self.assertEqual(self.fixture.request("post", f"{path}{task.pk}/state/", {"state_code": "EN_CURSO"}, self.fixture.worker).status_code, 403)
