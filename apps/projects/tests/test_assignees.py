import json
import os
import unittest
from importlib import import_module

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test.utils import CaptureQueriesContext

from apps.projects.models import ProjectMember, Task, TaskAssignee, TaskLabel
from apps.workers.models import WorkerArea
from . import test_projects as fixtures


class MultipleTaskAssigneeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProjectFlowTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.ProjectFlowTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.ProjectFlowTests()
        self.fixture.setUp()
        self.colleague = self.fixture.account("colleague", "TRABAJADOR", self.fixture.area)
        self.project = self.fixture.project(
            mode="assigned", worker_ids=[self.fixture.worker.worker_id, self.colleague.worker_id],
            worker_contribute=True, worker_edit=True, worker_state=True,
        )

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, **changes):
        return self.fixture.request("post", f"{self.project.pk}/tasks/", self.fixture.task_payload(**changes), self.fixture.admin)

    def patch(self, task_id, data, user=None):
        return self.fixture.request("patch", f"{self.project.pk}/tasks/{task_id}/", data, user or self.fixture.admin)

    def listed(self, user):
        return self.fixture.request("get", f"{self.project.pk}/tasks/", user=user)

    def test_multiple_assignments_are_real_visible_and_editable_without_duplicates(self):
        ids = [self.fixture.worker.worker_id, self.colleague.worker_id]
        response = self.create(responsible_ids=list(reversed(ids)))
        self.assertEqual(response.status_code, 201, response.content)
        task_id = response.json()["id"]
        self.assertEqual([person["id"] for person in response.json()["assignees"]], ids)
        self.assertEqual(TaskAssignee.objects.filter(task_id=task_id).count(), 1)
        for user in (self.fixture.worker, self.colleague):
            listing = self.listed(user)
            self.assertEqual([task["id"] for task in listing.json()], [task_id])
            self.assertTrue(listing.json()[0]["permissions"]["edit"])
            self.assertEqual(self.patch(task_id, {"name": "Compartida"}, user).status_code, 200)
        self.assertEqual(self.listed(self.fixture.outsider).status_code, 404)
        changed = self.fixture.request("post", f"{self.project.pk}/tasks/{task_id}/state/",
                                       {"state_code": "EN_CURSO", "reason": ""}, self.colleague)
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(self.listed(self.fixture.worker).json()[0]["state_code"], "EN_CURSO")

    def test_legacy_primary_contract_is_compatible_and_assignment_can_be_cleared(self):
        response = self.create(responsible_id=self.fixture.worker.worker_id)
        task_id = response.json()["id"]
        self.assertEqual([p["id"] for p in response.json()["assignees"]], [self.fixture.worker.worker_id])
        changed = self.patch(task_id, {"responsible_ids": [self.colleague.worker_id, self.fixture.worker.worker_id]})
        self.assertEqual(changed.json()["responsible_id"], self.fixture.worker.worker_id)
        changed = self.patch(task_id, {"responsible_id": self.colleague.worker_id})
        self.assertEqual([p["id"] for p in changed.json()["assignees"]], [self.colleague.worker_id])
        self.assertEqual(TaskAssignee.objects.count(), 0)
        self.assertEqual(self.listed(self.fixture.worker).json(), [])
        changed = self.patch(task_id, {"responsible_ids": []})
        self.assertEqual(changed.json()["assignees"], [])
        self.assertIsNone(changed.json()["responsible_id"])

    def test_invalid_or_unauthorized_assignments_are_rejected_atomically(self):
        for changes in (
            {"responsible_ids": [self.fixture.worker.worker_id] * 2},
            {"responsible_ids": [self.fixture.outsider.worker_id]},
            {"responsible_ids": [999999]},
            {"responsible_ids": None},
            {"responsible_ids": [], "responsible_id": self.fixture.worker.worker_id},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes).status_code, 400)
                self.assertEqual(Task.objects.count(), 0)
        response = self.create(responsible_ids=[self.fixture.worker.worker_id, self.colleague.worker_id])
        task_id = response.json()["id"]
        self.assertEqual(self.patch(task_id, {"responsible_ids": []}, self.colleague).status_code, 403)
        self.assertEqual(TaskAssignee.objects.count(), 1)
        payload = self.fixture.task_payload(responsible_ids=[self.colleague.worker_id])
        self.assertEqual(self.fixture.request("post", f"{self.project.pk}/tasks/", payload, self.fixture.worker).status_code, 403)

    def test_revoked_membership_area_account_and_flags_still_deny_mutations(self):
        response = self.create(responsible_ids=[self.fixture.worker.worker_id, self.colleague.worker_id])
        task_id = response.json()["id"]
        ProjectMember.objects.filter(project=self.project, worker=self.colleague.worker).update(active=False)
        self.assertEqual(self.listed(self.colleague).status_code, 404)
        self.assertEqual(self.patch(task_id, {"name": "No"}, self.colleague).status_code, 404)
        ProjectMember.objects.filter(project=self.project, worker=self.colleague.worker).update(active=True)
        WorkerArea.objects.create(worker=self.colleague.worker, area=self.fixture.other_area)
        self.assertEqual(self.listed(self.colleague).status_code, 404)
        WorkerArea.objects.filter(worker=self.colleague.worker).delete()
        self.project.worker_edit = False
        self.project.save(update_fields=["worker_edit"])
        self.assertFalse(self.listed(self.colleague).json()[0]["permissions"]["edit"])
        self.assertEqual(self.patch(task_id, {"name": "No"}, self.colleague).status_code, 403)
        self.colleague.is_active = False
        self.colleague.save(update_fields=["is_active"])
        self.assertEqual(self.listed(self.colleague).status_code, 401)

    def test_unchanged_labels_keep_their_ids_across_edits(self):
        response = self.create(labels=[{"name": "Python", "kind": "technical"}])
        task_id = response.json()["id"]
        label_id = response.json()["labels"][0]["id"]
        changed = self.patch(task_id, {"priority": 2, "labels": [{"name": "Python", "kind": "technical"}], "requirement_ids": []})
        self.assertEqual(changed.json()["labels"][0]["id"], label_id)
        self.assertEqual(TaskLabel.objects.count(), 1)

    def test_query_count_is_constant_with_secondary_assignees_and_does_not_paginate(self):
        self.assertEqual(self.listed(self.colleague).status_code, 200)
        counts = []
        for size in (1, 20, 100):
            for number in range(Task.objects.count(), size):
                response = self.create(name=f"Compartida {number}", responsible_ids=[self.fixture.worker.worker_id, self.colleague.worker_id])
                self.assertEqual(response.status_code, 201)
            with CaptureQueriesContext(connection) as captured:
                response = self.listed(self.colleague)
            counts.append(len(captured))
            self.assertEqual(len(response.json()), size)
            self.assertTrue(all(len(task["assignees"]) == 2 for task in response.json()))
        self.assertEqual(len(set(counts)), 1, counts)
        self.assertLessEqual(max(counts), 25)
        self.assertIsInstance(json.loads(response.content), list)


class TaskAssigneeMigrationTests(unittest.TestCase):
    def test_migration_creates_only_new_table_and_does_not_rewrite_primary_assignees(self):
        if os.environ.get("AUTH_TEST_SQLITE") != "1" or connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
            raise unittest.SkipTest("Requires explicit isolated SQLite memory settings")
        self.assertEqual(connection.introspection.table_names(), [])
        module = import_module("apps.projects.migrations.0009_task_assignees")
        migration = module.Migration("0009_task_assignees", "proyectos")
        state = MigrationLoader(None).project_state([("proyectos", "0008_project_favorite")])
        with connection.schema_editor() as editor:
            migrated = migration.apply(state, editor)
        self.assertEqual(connection.introspection.table_names(), ["actividad_responsable_adicional"])
        assignees = migrated.apps.get_model("proyectos", "TaskAssignee")
        assignees.objects.create(task_id=42, worker_id=12)
        with self.assertRaisesRegex(RuntimeError, "Additional assignees exist"):
            with connection.schema_editor() as editor:
                migration.unapply(state, editor)
        self.assertEqual(assignees.objects.count(), 1)
        assignees.objects.all().delete()
        with connection.schema_editor() as editor:
            migration.unapply(state, editor)
        self.assertEqual(connection.introspection.table_names(), [])

    def test_sql_preserves_existing_validations_except_authorized_assignee_expansion(self):
        module = import_module("apps.projects.migrations.0009_task_assignees")
        sql = module.source()
        restored = sql.replace(" DECLARE v_asignado BOOLEAN DEFAULT FALSE;\n", "")
        restored = restored.replace(" SET v_asignado=(v_responsable<=>v_persona) OR EXISTS(SELECT 1 FROM actividad_responsable_adicional\n WHERE actividad_id=p_actividad AND trabajador_id=v_persona);\n", "")
        restored = restored.replace("v_asignado=0", "NOT(v_responsable<=>v_persona)")
        self.assertEqual(module.baseline.normalized(restored), module.baseline.normalized(module.baseline.source()))
