import json
import os
import unittest
from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import Client
from django.utils import timezone

from apps.autenticacion.models import AuthToken, Role, User, UserRole
from apps.organization.models import Area
from apps.workers.models import Worker, WorkerArea
from apps.autenticacion.tokens import issue_access
from apps.proyectos.models import Project, ProjectArea, ProjectMember, ProjectRequirement, ProjectState, ProjectType, Task, TaskDependency, TaskLabel, TaskState, TaskTransition
from apps.proyectos.services.tasks import dependency_would_cycle


class ProjectFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("AUTH_TEST_SQLITE") != "1" or connection.vendor != "sqlite":
            raise unittest.SkipTest("Project tests require the existing explicit isolated SQLite mode")
        cls.tables = [Area, Worker, WorkerArea, User, Role, UserRole, AuthToken, ProjectType, ProjectState, TaskState, TaskTransition, Project, ProjectArea, ProjectMember, ProjectRequirement, Task, TaskDependency, TaskLabel]
        with connection.schema_editor() as editor:
            for model in cls.tables:
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(cls.tables):
                editor.delete_model(model)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.area = Area.objects.create(code="TEST_A", name="Área sintética A", active=True)
        self.other_area = Area.objects.create(code="TEST_B", name="Área sintética B", active=True)
        self.inactive_area = Area.objects.create(code="TEST_OFF", name="Área sintética inactiva", active=False)
        for code, name in (("ADMINISTRADOR", "Administrador"), ("TRABAJADOR", "Trabajador")):
            Role.objects.create(code=code, name=name)
        ProjectType.objects.create(code="GENERAL", name="General")
        ProjectState.objects.create(code="PLANIFICADO", name="Planificado")
        for code in ("PENDIENTE", "EN_CURSO", "EN_REVISION", "OBSERVADA", "COMPLETADA", "BLOQUEADA", "CANCELADA"):
            TaskState.objects.create(code=code, name=code, terminal=code in ("COMPLETADA", "CANCELADA"))
        for source, target, supervision, reason in (
            ("PENDIENTE", "EN_CURSO", False, False), ("PENDIENTE", "BLOQUEADA", False, True),
            ("PENDIENTE", "CANCELADA", True, True), ("EN_CURSO", "EN_REVISION", False, False),
            ("EN_REVISION", "COMPLETADA", True, False), ("COMPLETADA", "EN_CURSO", True, True),
        ):
            TaskTransition.objects.create(source=source, target=target, supervision_required=supervision, reason_required=reason)
        self.admin = self.account("admin", "ADMINISTRADOR", self.other_area)
        self.worker = self.account("worker", "TRABAJADOR", self.area)
        self.outsider = self.account("outsider", "TRABAJADOR", self.other_area)
        self.tokens = {}
        self.today = timezone.localdate()

    def tearDown(self):
        with connection.cursor() as cursor:
            for model in reversed(self.tables):
                cursor.execute(f'DELETE FROM "{model._meta.db_table}"')

    def account(self, code, role, area, active=True):
        worker = Worker.objects.create(code=code, area=area, first_names="Nombre sintético", last_names=code, email=f"{code}@example.invalid", active=True)
        user = User.objects.create(worker=worker, username=f"test_{code}", password="!", is_active=active)
        UserRole.objects.create(user=user, role_code=role)
        return user

    def request(self, method, path="", data=None, user=None):
        headers = {}
        if user:
            if user.pk not in self.tokens:
                self.tokens[user.pk] = issue_access(user, timezone.now() + timedelta(hours=1))
            headers["HTTP_AUTHORIZATION"] = f"Bearer {self.tokens[user.pk]}"
        kwargs = {"content_type": "application/json", **headers}
        if data is not None:
            kwargs["data"] = json.dumps(data)
        return getattr(self.client, method)(f"/api/projects/{path}", **kwargs)

    def project_payload(self, **changes):
        return {"name": "Proyecto sintético", "area_ids": [self.area.pk], "mode": "available", **changes}

    def project(self, **changes):
        response = self.request("post", data=self.project_payload(**changes), user=self.admin)
        self.assertEqual(response.status_code, 201, response.content)
        return Project.objects.get(pk=response.json()["id"])

    def assigned_project(self, **changes):
        return self.project(mode="assigned", worker_ids=[self.worker.worker_id], start_date=str(self.today), end_date=str(self.today + timedelta(days=30)), **changes)

    def task_payload(self, **changes):
        return {"name": "Tarea sintética", "state_code": "PENDIENTE", "priority": 3, "due_date": str(self.today + timedelta(days=10)), **changes}

    def task(self, project, **changes):
        response = self.request("post", f"{project.pk}/tasks/", self.task_payload(**changes), self.admin)
        self.assertEqual(response.status_code, 201, response.content)
        return Task.objects.get(pk=response.json()["id"])

    def test_all_endpoints_require_existing_authentication(self):
        project = self.project()
        task = self.task(project)
        for method, path, data in (
            ("get", "", None), ("get", "catalogs/", None), ("get", "workers/", None),
            ("post", "", self.project_payload()), ("get", f"{project.pk}/", None),
            ("get", f"{project.pk}/tasks/", None), ("post", f"{project.pk}/tasks/", self.task_payload()),
            ("patch", f"{project.pk}/tasks/{task.pk}/", {"name": "Cambio"}),
            ("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}),
            ("post", f"{project.pk}/tasks/{task.pk}/dependencies/", {"predecessor_id": task.pk}),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, data).status_code, 401)

    def test_available_creation_persists_areas_labels_defaults_without_members_or_dates(self):
        project = self.project(area_ids=[self.area.pk, self.other_area.pk], requirements=[{"name": "Texto <script>no ejecutable</script>", "kind": "technical"}])
        self.assertEqual(set(ProjectArea.objects.filter(project=project).values_list("area_id", flat=True)), {self.area.pk, self.other_area.pk})
        self.assertEqual(project.area_id, self.area.pk)
        self.assertIsNone(project.start_date)
        self.assertIsNone(project.end_date)
        self.assertFalse(project.worker_edit)
        self.assertFalse(project.worker_state)
        self.assertTrue(project.available)
        self.assertFalse(ProjectMember.objects.filter(project=project).exists())
        self.assertEqual(ProjectRequirement.objects.get(project=project).name, "Texto <script>no ejecutable</script>")

    def test_assigned_creation_is_atomic_and_uses_project_membership_not_global_roles(self):
        project = self.assigned_project(worker_edit=True)
        self.assertFalse(project.available)
        self.assertTrue(project.worker_edit)
        self.assertFalse(project.worker_state)
        self.assertEqual(ProjectMember.objects.get(project=project).worker_id, self.worker.worker_id)
        self.assertEqual(self.worker.global_role, "TRABAJADOR")

    def test_creation_rolls_back_all_records_on_requirement_failure(self):
        with patch("apps.proyectos.services.projects.ProjectRequirement.objects.bulk_create", side_effect=IntegrityError("synthetic failure")):
            response = self.request("post", data=self.project_payload(mode="assigned", worker_ids=[self.worker.worker_id], start_date=str(self.today), end_date=str(self.today + timedelta(days=30)), requirements=[{"name": "Requisito", "kind": "technical"}]), user=self.admin)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Project.objects.exists())
        self.assertFalse(ProjectArea.objects.exists())
        self.assertFalse(ProjectMember.objects.exists())

    def test_bad_project_payloads_never_create_partial_records(self):
        for changes in (
            {"name": " "}, {"area_ids": []}, {"area_ids": [self.inactive_area.pk]},
            {"area_ids": [self.area.pk, self.area.pk]}, {"area_ids": [999999]},
            {"mode": "assigned", "worker_ids": [self.worker.worker_id]},
            {"mode": "available", "worker_ids": [self.worker.worker_id]},
            {"mode": "assigned", "worker_ids": [self.outsider.worker_id], "start_date": str(self.today), "end_date": str(self.today + timedelta(days=10))},
            {"start_date": str(self.today), "end_date": str(self.today - timedelta(days=1))},
            {"requirements": [{"name": "Igual", "kind": "technical"}, {"name": "igual", "kind": "technical"}]},
            {"global_role": "ADMINISTRADOR"},
        ):
            with self.subTest(changes=changes):
                response = self.request("post", data=self.project_payload(**changes), user=self.admin)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertFalse(Project.objects.exists())

    def test_only_admin_can_create_projects_and_fetch_worker_candidates(self):
        self.assertEqual(self.request("post", data=self.project_payload(worker_edit=True, worker_state=True), user=self.worker).status_code, 403)
        self.assertEqual(self.request("get", f"workers/?area_ids={self.area.pk}", user=self.worker).status_code, 403)
        self.assertEqual(self.request("get", "catalogs/", user=self.worker).json()["areas"], [])
        self.assertEqual({area["id"] for area in self.request("get", "catalogs/", user=self.admin).json()["areas"]}, {self.area.pk, self.other_area.pk})

    def test_available_project_visibility_requires_authorized_area_and_honors_revocation(self):
        project = self.project()
        self.assertEqual(self.request("get", f"{project.pk}/", user=self.worker).status_code, 200)
        self.assertEqual(self.request("get", f"{project.pk}/", user=self.outsider).status_code, 404)
        ProjectMember.objects.create(project=project, worker=self.worker.worker, active=False)
        self.assertEqual(self.request("get", f"{project.pk}/", user=self.worker).status_code, 404)
        self.assertEqual(self.request("get", user=self.outsider).json(), [])

    def test_assigned_and_confidential_projects_require_participation_and_area(self):
        assigned = self.assigned_project()
        extra = self.account("same_area", "TRABAJADOR", self.area)
        self.assertEqual(self.request("get", f"{assigned.pk}/", user=extra).status_code, 404)
        public = self.project()
        public.confidential = True
        public.save()
        self.assertEqual(self.request("get", f"{public.pk}/", user=self.worker).status_code, 404)
        ProjectMember.objects.create(project=public, worker=self.worker.worker)
        self.assertEqual(self.request("get", f"{public.pk}/", user=self.worker).status_code, 200)
        self.worker.worker.area = self.other_area
        self.worker.worker.save()
        self.assertEqual(self.request("get", f"{assigned.pk}/", user=self.worker).status_code, 404)

    def test_all_areas_and_multiple_areas_use_existing_backend_resolution(self):
        self.worker.worker.all_areas = True
        self.worker.worker.area = None
        self.worker.worker.save()
        new_area = Area.objects.create(code="TEST_NEW", name="Área futura sintética", active=True)
        project = self.project(area_ids=[new_area.pk])
        self.assertEqual(self.request("get", f"{project.pk}/", user=self.worker).status_code, 200)
        WorkerArea.objects.create(worker=self.outsider.worker, area=self.area)
        candidates = self.request("get", f"workers/?area_ids={self.area.pk}&q=Nombre%20outsider", user=self.admin)
        self.assertEqual(candidates.status_code, 200)
        self.assertEqual([item["id"] for item in candidates.json()], [self.outsider.worker_id])
        self.assertEqual(set(candidates.json()[0]), {"id", "name", "project_count"})

    def test_worker_search_counts_memberships_and_excludes_inactive_accounts(self):
        self.assigned_project()
        inactive = self.account("inactive", "TRABAJADOR", self.area, active=False)
        response = self.request("get", f"workers/?area_ids={self.area.pk}", user=self.admin)
        self.assertEqual(response.status_code, 200)
        result = {item["id"]: item for item in response.json()}
        self.assertEqual(result[self.worker.worker_id]["project_count"], 1)
        self.assertNotIn(inactive.worker_id, result)
        self.assertEqual(self.request("get", "workers/?area_ids=invalid", user=self.admin).status_code, 400)

    def test_admin_can_create_unassigned_tasks_without_a_phase_or_project_membership(self):
        project = self.project()
        task = self.task(project, labels=[{"name": "Propia", "kind": "nontechnical"}])
        self.assertIsNone(task.phase_id)
        self.assertIsNone(task.responsible_id)
        self.assertIsNotNone(task.created_at)
        self.assertEqual(TaskLabel.objects.get(task=task).name, "Propia")
        self.assertFalse(ProjectMember.objects.filter(project=project, worker=self.admin.worker).exists())

    def test_task_creation_validates_catalog_responsible_dates_and_foreign_requirements(self):
        project = self.project()
        other = self.project(requirements=[{"name": "Ajeno", "kind": "technical"}])
        requirement = ProjectRequirement.objects.get(project=other)
        for changes in (
            {"state_code": "INVALID"}, {"priority": 5}, {"due_date": str(self.today - timedelta(days=1))},
            {"responsible_id": self.worker.worker_id}, {"state_code": "EN_CURSO"},
            {"state_code": "BLOQUEADA"}, {"requirement_ids": [requirement.pk]},
            {"created_at": "2020-01-01"}, {"parent_id": 999999},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.request("post", f"{project.pk}/tasks/", self.task_payload(**changes), self.admin).status_code, 400)
                self.assertFalse(Task.objects.filter(project=project).exists())

    def test_subtask_dates_and_parent_project_are_validated(self):
        project = self.assigned_project()
        parent = self.task(project, responsible_id=self.worker.worker_id)
        child = self.task(project, parent_id=parent.pk, responsible_id=self.worker.worker_id)
        self.assertEqual(child.parent_id, parent.pk)
        self.assertIsNone(child.phase_id)
        other = self.project()
        self.assertEqual(self.request("post", f"{other.pk}/tasks/", self.task_payload(parent_id=parent.pk), self.admin).status_code, 400)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/", self.task_payload(parent_id=parent.pk, due_date=str(self.today + timedelta(days=11))), self.admin).status_code, 400)
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{parent.pk}/", {"due_date": str(self.today + timedelta(days=5))}, self.admin).status_code, 400)

    def test_default_worker_flags_deny_direct_edit_and_state_for_tasks_and_subtasks(self):
        project = self.assigned_project()
        parent = self.task(project, responsible_id=self.worker.worker_id)
        child = self.task(project, parent_id=parent.pk, responsible_id=self.worker.worker_id)
        for task in (parent, child):
            self.assertEqual(self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"name": "Prohibido"}, self.worker).status_code, 403)
            self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.worker).status_code, 403)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/", self.task_payload(), self.worker).status_code, 403)
        self.assertEqual(self.request("delete", f"{project.pk}/tasks/{parent.pk}/", user=self.worker).status_code, 405)

    def test_worker_edit_flag_is_independent_from_state_flag_and_cannot_change_responsible(self):
        project = self.assigned_project(worker_edit=True, requirements=[{"name": "Base", "kind": "technical"}])
        task = self.task(project, responsible_id=self.worker.worker_id)
        requirement = ProjectRequirement.objects.get(project=project)
        response = self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"name": "Editada", "priority": 2, "due_date": str(self.today + timedelta(days=9)), "requirement_ids": [requirement.pk], "labels": [{"name": "Extra", "kind": "nontechnical"}]}, self.worker)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["labels"]), 2)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.worker).status_code, 403)
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"responsible_id": None}, self.worker).status_code, 403)
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"state_code": "EN_CURSO"}, self.worker).status_code, 400)

    def test_worker_state_flag_is_independent_from_edit_flag(self):
        project = self.assigned_project(worker_state=True)
        task = self.task(project, responsible_id=self.worker.worker_id)
        response = self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.worker)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state_code"], "EN_CURSO")
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"name": "Prohibido"}, self.worker).status_code, 403)

    def test_worker_flags_apply_to_assigned_subtasks(self):
        project = self.assigned_project(worker_edit=True, worker_state=True)
        parent = self.task(project)
        child = self.task(project, parent_id=parent.pk, responsible_id=self.worker.worker_id)
        response = self.request("get", f"{project.pk}/tasks/", user=self.worker)
        self.assertEqual([item["id"] for item in response.json()], [child.pk])
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{child.pk}/", {"name": "Subtarea editada"}, self.worker).status_code, 200)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{child.pk}/state/", {"state_code": "EN_CURSO"}, self.worker).status_code, 200)
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{parent.pk}/", {"name": "Padre ajeno"}, self.worker).status_code, 404)

    def test_worker_visibility_and_assignment_cannot_be_overridden_by_filters(self):
        project = self.assigned_project(worker_edit=True, worker_state=True)
        own = self.task(project, responsible_id=self.worker.worker_id)
        unassigned = self.task(project)
        self.assertEqual([item["id"] for item in self.request("get", f"{project.pk}/tasks/?responsible_id=all&role=ADMINISTRADOR", user=self.worker).json()], [own.pk])
        self.assertEqual(self.request("patch", f"{project.pk}/tasks/{unassigned.pk}/", {"name": "Intento"}, self.worker).status_code, 404)
        ProjectMember.objects.filter(project=project, worker=self.worker.worker).update(active=False)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{own.pk}/state/", {"state_code": "EN_CURSO"}, self.worker).status_code, 404)

    def test_admin_supervises_globally_but_worker_needs_project_supervision_and_own_assignment(self):
        project = self.assigned_project(worker_state=True)
        task = self.task(project, state_code="EN_REVISION", responsible_id=self.worker.worker_id)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "COMPLETADA"}, self.worker).status_code, 403)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "COMPLETADA"}, self.admin).status_code, 200)
        self.assertFalse(ProjectMember.objects.filter(project=project, worker=self.admin.worker).exists())

    def test_state_requires_valid_transition_reason_dependencies_and_responsible(self):
        project = self.assigned_project(worker_state=True)
        task = self.task(project)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.admin).status_code, 400)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "BLOQUEADA"}, self.admin).status_code, 400)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "COMPLETADA"}, self.admin).status_code, 400)
        successor = self.task(project, responsible_id=self.worker.worker_id)
        TaskDependency.objects.create(project=project, predecessor=task, successor=successor)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{successor.pk}/state/", {"state_code": "EN_CURSO"}, self.worker).status_code, 400)

    def test_dependencies_allow_later_created_and_dated_predecessors_and_parent_tasks(self):
        project = self.project()
        first = self.task(project, due_date=str(self.today + timedelta(days=2)))
        later = self.task(project, due_date=str(self.today + timedelta(days=20)))
        self.task(project, parent_id=later.pk)
        response = self.request("post", f"{project.pk}/tasks/{first.pk}/dependencies/", {"predecessor_id": later.pk}, self.admin)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(TaskDependency.objects.get(project=project).predecessor_id, later.pk)
        self.assertEqual(self.request("delete", f"{project.pk}/tasks/{first.pk}/dependencies/", {"predecessor_id": later.pk}, self.admin).status_code, 204)
        self.assertFalse(TaskDependency.objects.exists())

    def test_dependencies_reject_self_cross_project_subtasks_duplicate_and_cycles(self):
        project = self.project()
        first = self.task(project)
        second = self.task(project)
        third = self.task(project)
        child = self.task(project, parent_id=first.pk)
        foreign = self.task(self.project())
        for source, target, expected in ((first, first, 400), (foreign, first, 404), (child, first, 400), (first, child, 400)):
            self.assertEqual(self.request("post", f"{project.pk}/tasks/{target.pk}/dependencies/", {"predecessor_id": source.pk}, self.admin).status_code, expected)
        for source, target in ((first, second), (second, third)):
            self.assertEqual(self.request("post", f"{project.pk}/tasks/{target.pk}/dependencies/", {"predecessor_id": source.pk}, self.admin).status_code, 201)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{first.pk}/dependencies/", {"predecessor_id": third.pk}, self.admin).status_code, 400)
        self.assertEqual(self.request("post", f"{project.pk}/tasks/{second.pk}/dependencies/", {"predecessor_id": first.pk}, self.admin).status_code, 400)
        self.assertEqual(TaskDependency.objects.count(), 2)

    def test_workers_never_manage_dependencies_even_with_both_flags(self):
        project = self.assigned_project(worker_edit=True, worker_state=True)
        first = self.task(project, responsible_id=self.worker.worker_id)
        second = self.task(project, responsible_id=self.worker.worker_id)
        for method in ("post", "delete"):
            self.assertEqual(self.request(method, f"{project.pk}/tasks/{second.pk}/dependencies/", {"predecessor_id": first.pk}, self.worker).status_code, 403)

    def test_project_update_delete_and_task_delete_are_not_exposed(self):
        project = self.project()
        task = self.task(project)
        for method, path in (("patch", f"{project.pk}/"), ("delete", f"{project.pk}/"), ("delete", f"{project.pk}/tasks/{task.pk}/")):
            self.assertEqual(self.request(method, path, {}, self.admin).status_code, 405)

    def test_cors_remains_explicit_and_allows_required_methods_only(self):
        from django.conf import settings
        response = self.client.options("/api/projects/", HTTP_ORIGIN=settings.FRONTEND_ORIGIN)
        self.assertIn("PATCH", response["Access-Control-Allow-Methods"])
        self.assertEqual(response["Access-Control-Allow-Origin"], settings.FRONTEND_ORIGIN)
        denied = self.client.options("/api/projects/", HTTP_ORIGIN="https://untrusted.invalid")
        self.assertNotIn("Access-Control-Allow-Origin", denied)

    def test_task_labels_fail_atomically_without_persisting_task(self):
        project = self.project(requirements=[{"name": "Base", "kind": "technical"}])
        requirement = ProjectRequirement.objects.get(project=project)
        response = self.request("post", f"{project.pk}/tasks/", self.task_payload(requirement_ids=[requirement.pk], labels=[{"name": "base", "kind": "technical"}]), self.admin)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())
        self.assertFalse(TaskLabel.objects.exists())

    def test_area_relationships_are_authoritative_over_legacy_primary_area(self):
        WorkerArea.objects.create(worker=self.worker.worker, area=self.other_area)
        project = self.project()
        self.assertEqual(self.request("get", f"{project.pk}/", user=self.worker).status_code, 404)
        other = self.project(area_ids=[self.other_area.pk])
        self.assertEqual(self.request("get", f"{other.pk}/", user=self.worker).status_code, 200)
        candidates = self.request("get", f"workers/?area_ids={self.area.pk}", user=self.admin).json()
        self.assertNotIn(self.worker.worker_id, {item["id"] for item in candidates})

    def test_final_projects_reject_mutations_and_hide_management_actions(self):
        project = self.assigned_project(worker_edit=True, worker_state=True)
        task = self.task(project, responsible_id=self.worker.worker_id)
        project.state_code = "FINALIZADO"
        project.save()
        for user in (self.admin, self.worker):
            self.assertEqual(self.request("patch", f"{project.pk}/tasks/{task.pk}/", {"name": "No"}, user).status_code, 400)
            response = self.request("get", f"{project.pk}/tasks/", user=user)
            self.assertFalse(response.json()[0]["permissions"]["edit"])
            self.assertFalse(response.json()[0]["permissions"]["state"])
            self.assertFalse(response.json()[0]["permissions"]["create_child"])

    def test_mysql_path_calls_existing_state_procedure_with_authenticated_context(self):
        from apps.proyectos.services.tasks import change_task_state
        project = self.assigned_project(worker_state=True)
        task = self.task(project, responsible_id=self.worker.worker_id)
        with patch("apps.proyectos.services.tasks.connection") as database:
            database.vendor = "mysql"
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.nextset.return_value = False
            def apply_state(name, parameters):
                self.assertFalse(connection.in_atomic_block)
                Task.objects.filter(pk=parameters[1]).update(state_code=parameters[2])
            cursor.callproc.side_effect = apply_state
            result = change_task_state(self.worker, project.pk, task.pk, {"state_code": "EN_CURSO", "reason": ""})
            cursor.callproc.assert_called_once_with("sp_cambiar_estado_actividad", [project.pk, task.pk, "EN_CURSO", None])
            self.assertEqual(result.state_code, "EN_CURSO")


class ProjectPolicyTests(unittest.TestCase):
    def test_cycle_detection_does_not_depend_on_order(self):
        self.assertTrue(dependency_would_cycle([(3, 2), (2, 1)], 1, 3))
        self.assertFalse(dependency_would_cycle([(3, 2)], 1, 3))

    def test_sql_policy_preserves_deliverable_and_hierarchy_checks(self):
        policy = import_module("apps.proyectos.migrations.0003_project_sql_policy")
        state = policy.source("sp_cambiar_estado_actividad")
        self.assertIn("v_estado_entregable", state)
        self.assertIn("Hay subtareas incompatibles", state)
        self.assertIn("trabajador_cambia_estado=1", state)
        self.assertIn("NOT(v_responsable<=>v_persona)", state)
        self.assertIn("proyecto_area", state)
        dependencies = policy.source("sp_agregar_dependencia")
        self.assertNotIn("s.fecha_inicio<p.fecha_fin", dependencies)
        self.assertIn("padre_id IS NOT NULL", dependencies)
        self.assertIn("v_ciclo>0", dependencies)
        self.assertIn("rol_codigo='ADMINISTRADOR'", dependencies)

    def test_schema_reverse_refuses_data_loss(self):
        schema = import_module("apps.proyectos.migrations.0002_project_schema")
        with patch("django.db.connection.cursor") as cursor_factory:
            cursor = cursor_factory.return_value
            cursor.fetchone.return_value = (1,)
            with self.assertRaises(RuntimeError):
                schema.ensure_unused(cursor)

    def test_audit_identity_is_authenticated_and_cleared_after_failure(self):
        from apps.proyectos.services.audit import audit_actor
        with patch("apps.proyectos.services.audit.connection") as database:
            database.vendor = "mysql"
            with patch("apps.proyectos.services.audit.connection.cursor") as cursor_factory:
                actor = unittest.mock.Mock(pk=41, global_role="ADMINISTRADOR")
                with self.assertRaises(ValueError):
                    with audit_actor(actor):
                        raise ValueError("synthetic failure")
                cursor = cursor_factory.return_value.__enter__.return_value
                self.assertEqual(cursor.execute.call_args_list[0].args, ("SET @gm_usuario_id = %s", [41]))
                self.assertEqual(cursor.execute.call_args_list[-1].args, ("SET @gm_usuario_id = NULL",))
