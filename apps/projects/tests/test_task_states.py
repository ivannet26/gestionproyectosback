import unittest
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.db import DatabaseError, IntegrityError

from apps.projects.models import Project, ProjectMember, ProjectTaskStatus, Task, TaskLabel
from . import test_projects as fixtures


class TaskStateFlowTests(unittest.TestCase):
    setUp = fixtures.ProjectFlowTests.setUp
    tearDown = fixtures.ProjectFlowTests.tearDown
    account = fixtures.ProjectFlowTests.account
    request = fixtures.ProjectFlowTests.request
    project_payload = fixtures.ProjectFlowTests.project_payload
    project = fixtures.ProjectFlowTests.project
    assigned_project = fixtures.ProjectFlowTests.assigned_project
    task_payload = fixtures.ProjectFlowTests.task_payload
    task = fixtures.ProjectFlowTests.task

    @classmethod
    def setUpClass(cls):
        fixtures.ProjectFlowTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.ProjectFlowTests.tearDownClass.__func__(cls)

    def configuration(self, project, user=None):
        response = self.request("get", f"{project.pk}/task-states/", user=user or self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def configure(self, project, states=None, user=None, template="custom", revision=None):
        configuration = self.configuration(project)
        return self.request(
            "patch", f"{project.pk}/task-states/",
            {
                "template": template,
                "revision": revision or configuration["revision"],
                "states": states if states is not None else configuration["states"],
            },
            user or self.admin,
        )

    def test_standard_names_preserve_codes_and_review_transition(self):
        project = self.assigned_project()
        configuration = self.configuration(project)
        self.assertEqual(configuration["template"], "standard")
        self.assertEqual(
            configuration["states"][:3],
            [
                {"code": "PENDIENTE", "name": "PENDIENTE"},
                {"code": "EN_CURSO", "name": "EN CURSO"},
                {"code": "COMPLETADA", "name": "CERRADO"},
            ],
        )
        self.assertIn("EN_REVISION", {state["code"] for state in configuration["states"]})
        self.task(project, state_code="COMPLETADA", responsible_id=self.worker.worker_id)
        snapshot = self.request("get", f"{project.pk}/tasks/", user=self.admin).json()[0]
        self.assertEqual(snapshot["state_code"], "COMPLETADA")
        self.assertEqual(snapshot["state_name"], "CERRADO")
        self.assertFalse(ProjectTaskStatus.objects.exists())

    def test_description_persists_as_text_and_server_metadata_is_not_editable(self):
        project = self.project()
        description = "<script>texto sintético</script>"
        task = self.task(project, description=description)
        self.assertEqual(task.description, description)
        snapshot = self.request("get", f"{project.pk}/tasks/", user=self.admin).json()[0]
        self.assertEqual(snapshot["description"], description)
        self.assertTrue(snapshot["created_at"])
        for extra in ({"created_at": "2020-01-01"}, {"start_date": "2020-01-01"}, {"description": "x" * 10001}):
            with self.subTest(extra=list(extra)):
                response = self.request("post", f"{project.pk}/tasks/", self.task_payload(**extra), self.admin)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Task.objects.count(), 1)

    def test_description_labels_and_subtask_are_atomic(self):
        project = self.project()
        parent = self.task(project)
        payload = self.task_payload(
            parent_id=parent.pk, description="No persistir", labels=[{"name": "Sintética", "kind": "technical"}]
        )
        with patch("apps.projects.services.tasks.TaskLabel.objects.bulk_create", side_effect=IntegrityError("synthetic")):
            response = self.request("post", f"{project.pk}/tasks/", payload, self.admin)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Task.objects.count(), 1)
        self.assertFalse(TaskLabel.objects.exists())

    def test_description_does_not_expand_legacy_worker_edit_permissions(self):
        project = self.assigned_project(worker_edit=True, worker_contribute=True)
        task = self.task(project, responsible_id=self.worker.worker_id, description="Original")
        path = f"{project.pk}/tasks/{task.pk}/"
        response = self.request("patch", path, {"name": "Prohibido", "description": "Cambio"}, self.worker)
        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.description, "Original")
        self.assertNotEqual(task.name, "Prohibido")
        self.assertEqual(self.request("patch", path, {"name": "Permitido"}, self.worker).status_code, 200)
        response = self.request(
            "post", f"{project.pk}/tasks/", self.task_payload(description="Creación propia"), self.worker
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["responsible_id"], self.worker.worker_id)

    def test_responsibles_require_eligible_account_membership_and_area(self):
        project = self.assigned_project()
        inactive = self.account("inactive", "TRABAJADOR", self.area, active=False)
        for user in (inactive, self.outsider):
            ProjectMember.objects.create(project=project, worker=user.worker)
            response = self.request(
                "post", f"{project.pk}/tasks/", self.task_payload(responsible_id=user.worker_id), self.admin
            )
            self.assertEqual(response.status_code, 400)
        detail = self.request("get", f"{project.pk}/", user=self.admin).json()
        self.assertEqual([member["id"] for member in detail["participants"]], [self.worker.worker_id])

    def test_configuration_requires_authentication_admin_and_object_access(self):
        project = self.assigned_project()
        self.assertEqual(self.request("get", f"{project.pk}/task-states/").status_code, 401)
        self.assertEqual(self.request("patch", f"{project.pk}/task-states/", {}).status_code, 401)
        self.assertEqual(self.request("get", f"{project.pk}/task-states/", user=self.outsider).status_code, 404)
        self.assertFalse(self.configuration(project, self.worker)["can_configure"])
        self.assertEqual(self.configure(project, user=self.worker).status_code, 403)
        self.assertEqual(self.configure(project).status_code, 200)
        self.assertFalse(ProjectMember.objects.filter(project=project, worker=self.admin.worker).exists())

    def test_custom_names_order_are_scoped_without_rewriting_tasks(self):
        project = self.assigned_project()
        other = self.project()
        task = self.task(project, responsible_id=self.worker.worker_id)
        states = self.configuration(project)["states"]
        states = [
            {"code": state["code"], "name": "Por iniciar" if state["code"] == "PENDIENTE" else state["name"]}
            for state in reversed(states)
        ]
        response = self.configure(project, states)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.configuration(project)["states"], states)
        self.assertEqual(self.configuration(other)["template"], "standard")
        task.refresh_from_db()
        self.assertEqual(task.state_code, "PENDIENTE")
        snapshot = self.request("get", f"{project.pk}/tasks/", user=self.worker).json()[0]
        self.assertEqual(snapshot["state_name"], "Por iniciar")

    def test_invalid_names_codes_and_required_states_do_not_persist(self):
        project = self.project()
        states = self.configuration(project)["states"]
        for invalid in (
            [*states, states[0]],
            [{"code": state["code"], "name": "Duplicado"} for state in states],
            [*states, {"code": "NUEVO", "name": "Sin transición"}],
            [state for state in states if state["code"] != "PENDIENTE"],
            [{**state, "name": ""} for state in states],
            [],
        ):
            with self.subTest(states=invalid):
                self.assertEqual(self.configure(project, invalid).status_code, 400)
                self.assertFalse(ProjectTaskStatus.objects.exists())

    def test_used_archived_subtask_state_and_review_bridge_cannot_be_removed(self):
        project = self.project()
        parent = self.task(project)
        child = self.task(project, parent_id=parent.pk, state_code="OBSERVADA")
        child.archived = True
        child.save(update_fields=["archived"])
        for code in ("OBSERVADA", "EN_REVISION"):
            states = [state for state in self.configuration(project)["states"] if state["code"] != code]
            self.assertEqual(self.configure(project, states).status_code, 400)
        child.refresh_from_db()
        self.assertEqual(child.state_code, "OBSERVADA")
        self.assertFalse(ProjectTaskStatus.objects.exists())

    def test_unused_state_removal_is_enforced_on_creation_and_transition(self):
        project = self.assigned_project(worker_state=True)
        task = self.task(project, responsible_id=self.worker.worker_id)
        states = [state for state in self.configuration(project)["states"] if state["code"] != "BLOQUEADA"]
        self.assertEqual(self.configure(project, states).status_code, 200)
        response = self.request(
            "post", f"{project.pk}/tasks/", self.task_payload(state_code="BLOQUEADA", reason="Motivo"), self.admin
        )
        self.assertEqual(response.status_code, 400)
        snapshot = self.request("get", f"{project.pk}/tasks/", user=self.worker).json()[0]
        self.assertNotIn("BLOQUEADA", {item["target"] for item in snapshot["transitions"]})
        for user in (self.admin, self.worker):
            response = self.request(
                "post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "BLOQUEADA", "reason": "Motivo"}, user
            )
            self.assertEqual(response.status_code, 400)
        response = self.request(
            "post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.worker
        )
        self.assertEqual(response.status_code, 200)

    def test_stale_revision_and_failure_preserve_saved_configuration(self):
        project = self.project()
        before = self.configuration(project)
        states = [
            {**state, "name": "Inicio" if state["code"] == "PENDIENTE" else state["name"]}
            for state in before["states"]
        ]
        self.assertEqual(self.configure(project, states).status_code, 200)
        saved = self.configuration(project)
        self.assertEqual(self.configure(project, before["states"], revision=before["revision"]).status_code, 400)
        with patch("apps.projects.services.statuses.ProjectTaskStatus.objects.bulk_create", side_effect=IntegrityError("synthetic")):
            response = self.configure(project, list(reversed(states)))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.configuration(project), saved)

    def test_standard_reset_does_not_change_tasks_or_transitions(self):
        project = self.assigned_project()
        task = self.task(project, state_code="EN_REVISION", responsible_id=self.worker.worker_id)
        states = [
            {**state, "name": "Verificar" if state["code"] == "EN_REVISION" else state["name"]}
            for state in self.configuration(project)["states"]
        ]
        self.assertEqual(self.configure(project, states).status_code, 200)
        response = self.configure(project, [], template="standard")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProjectTaskStatus.objects.exists())
        task.refresh_from_db()
        self.assertEqual(task.state_code, "EN_REVISION")
        response = self.request(
            "post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "COMPLETADA"}, self.admin
        )
        self.assertEqual(response.status_code, 200)

    def test_closed_projects_reject_configuration_and_unknown_fields_are_rejected(self):
        project = self.project()
        configuration = self.configuration(project)
        response = self.request(
            "patch", f"{project.pk}/task-states/", {**configuration, "role": "ADMINISTRADOR"}, self.admin
        )
        self.assertEqual(response.status_code, 400)
        project.state_code = "FINALIZADO"
        project.save(update_fields=["state_code"])
        self.assertFalse(self.configuration(project)["can_configure"])
        self.assertEqual(self.configure(project).status_code, 400)

    def test_pending_state_schema_rejects_project_creation_before_writes(self):
        with patch("apps.projects.services.projects.ProjectTaskStatus.objects.exists", side_effect=DatabaseError("synthetic")):
            response = self.request("post", data=self.project_payload(), user=self.admin)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Project.objects.exists())


class TaskStateMigrationTests(unittest.TestCase):
    def test_sql_only_adds_guard_and_preserves_transaction_and_supervision(self):
        migration = import_module("apps.projects.migrations.0006_task_descriptions_and_project_states")
        previous = migration.source(False)
        updated = migration.source()
        guard = (
            " IF EXISTS(SELECT 1 FROM proyecto_estado_actividad WHERE proyecto_id=p_proyecto)\n"
            " AND NOT EXISTS(SELECT 1 FROM proyecto_estado_actividad WHERE proyecto_id=p_proyecto AND estado_codigo=p_destino) THEN\n"
            "  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Estado no habilitado en este proyecto.';\n"
            " END IF;\n"
        )
        self.assertEqual(updated.replace(guard, ""), previous)
        self.assertGreater(updated.index(guard), updated.index("FOR UPDATE"))
        self.assertEqual(migration.Migration.dependencies, [("proyectos", "0005_project_worker_create")])

    def test_reverse_refuses_description_or_configuration_data_loss_before_ddl(self):
        migration = import_module("apps.projects.migrations.0006_task_descriptions_and_project_states")
        for results in ([1], [0, 1]):
            cursor = Mock()
            cursor.fetchone.side_effect = [("text", "text", "YES", None, "", ""), *[(value,) for value in results]]
            connection = MagicMock(vendor="mysql", alias="isolated")
            connection.cursor.return_value.__enter__.return_value = cursor
            apps = Mock()
            apps.get_model.return_value.objects.using.return_value.get.return_value.payload = {
                "description_created": True
            }
            with self.subTest(results=results), self.assertRaises(RuntimeError):
                migration.restore(apps, SimpleNamespace(connection=connection))
            self.assertTrue(all(call.args[0].startswith("SELECT ") for call in cursor.execute.call_args_list))

    def test_reverse_restores_reviewed_procedure_when_unused(self):
        migration = import_module("apps.projects.migrations.0006_task_descriptions_and_project_states")
        cursor = Mock()
        cursor.fetchone.side_effect = [("text", "text", "YES", None, "", ""), (0,), (0,)]
        connection = MagicMock(vendor="mysql", alias="isolated")
        connection.cursor.return_value.__enter__.return_value = cursor
        apps = Mock()
        saved = apps.get_model.return_value.objects.using.return_value.get.return_value
        saved.payload = {"Create Procedure": "reviewed original", "description_created": True}
        with patch.object(migration, "review"), patch.object(migration.helpers, "recreate") as recreate:
            migration.restore(apps, SimpleNamespace(connection=connection))
        recreate.assert_called_once_with(cursor, migration.PROCEDURE, "reviewed original", saved.payload)
        cursor.execute.assert_called_with("ALTER TABLE actividad DROP COLUMN descripcion")
        saved.delete.assert_called_once()


class TaskDescriptionMigrationTests(unittest.TestCase):
    compatible_column = ("text", "text", "YES", None, "", "")

    def setUp(self):
        self.migration = import_module("apps.projects.migrations.0006_task_descriptions_and_project_states")
        self.cursor = Mock()
        connection = MagicMock(vendor="mysql", alias="isolated")
        connection.cursor.return_value.__enter__.return_value = self.cursor
        self.editor = SimpleNamespace(connection=connection)
        self.apps = Mock()
        self.backups = self.apps.get_model.return_value.objects.using.return_value
        self.saved = self.backups.create.return_value
        self.restored = self.backups.get.return_value
        self.definition = {"Create Procedure": self.migration.source(False), "sql_mode": "STRICT_TRANS_TABLES"}
        self.restored.payload = {**self.definition, "description_created": False}

        def save_backup(**kwargs):
            self.saved.payload = kwargs["payload"].copy()
            return self.saved

        self.backups.create.side_effect = save_backup

    def test_preflight_accepts_missing_or_compatible_description_without_writes(self):
        for column in (None, self.compatible_column):
            with self.subTest(column=column), patch.object(self.migration, "review") as review:
                self.cursor.reset_mock()
                self.cursor.fetchone.side_effect = [column, (0,)]
                self.migration.preflight(self.apps, self.editor)
                review.assert_called_once_with(self.cursor)
                self.assertTrue(all(call.args[0].startswith("SELECT ") for call in self.cursor.execute.call_args_list))
                self.assertEqual(self.cursor.execute.call_args_list[0].args[1], ["actividad", "descripcion"])
                self.backups.create.assert_not_called()

    def test_incompatible_column_definitions_are_rejected_before_writes(self):
        for column in (
            ("varchar", "varchar(255)", "YES", None, "", ""),
            ("mediumtext", "mediumtext", "YES", None, "", ""),
            ("text", "text", "NO", None, "", ""),
            ("text", "text", "YES", "default", "", ""),
            ("text", "text", "YES", None, "VIRTUAL GENERATED", "nombre"),
            ("text", "text", "YES", None, "", "nombre"),
        ):
            for operation in (self.migration.preflight, self.migration.install):
                with self.subTest(column=column, operation=operation.__name__), patch.object(
                    self.migration, "review", return_value=self.definition
                ):
                    self.cursor.reset_mock()
                    self.cursor.fetchone.side_effect = [column]
                    with self.assertRaisesRegex(RuntimeError, "TEXT NULL"):
                        operation(self.apps, self.editor)
                    self.assertEqual(self.cursor.execute.call_count, 1)
                    self.backups.create.assert_not_called()

    def test_existing_state_table_still_blocks_preflight(self):
        self.cursor.fetchone.side_effect = [self.compatible_column, (1,)]
        with patch.object(self.migration, "review"), self.assertRaisesRegex(RuntimeError, "state table already exists"):
            self.migration.preflight(self.apps, self.editor)
        self.assertTrue(all(call.args[0].startswith("SELECT ") for call in self.cursor.execute.call_args_list))

    def test_install_preserves_preexisting_column_and_records_ownership_false(self):
        self.cursor.fetchone.side_effect = [self.compatible_column, ("utf8mb4", "utf8mb4_unicode_ci")]
        with patch.object(self.migration, "review", return_value=self.definition), patch.object(
            self.migration.helpers, "recreate"
        ) as recreate:
            self.migration.install(self.apps, self.editor)
        self.backups.create.assert_called_once_with(
            key=self.migration.BACKUP_KEY, payload={**self.definition, "description_created": False}
        )
        self.apps.get_model.assert_called_once_with("autenticacion", "MigrationBackup")
        self.apps.get_model.return_value.objects.using.assert_called_once_with("isolated")
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any(statement.startswith("ALTER TABLE actividad ") for statement in statements))
        self.assertEqual(sum(statement.startswith("ALTER TABLE proyecto_estado_actividad ") for statement in statements), 1)
        self.assertIn("fk_proyecto_estado_proyecto", statements[-1])
        self.assertIn("fk_proyecto_estado_codigo", statements[-1])
        self.saved.save.assert_not_called()
        recreate.assert_called_once_with(self.cursor, self.migration.PROCEDURE, self.migration.source(), self.saved.payload)

    def test_install_creates_missing_column_once_and_marks_only_after_success(self):
        self.cursor.fetchone.side_effect = [None, ("utf8mb4", "utf8mb4_unicode_ci")]
        ownership_at_creation = []

        def execute(statement, *args):
            if statement == "ALTER TABLE actividad ADD COLUMN descripcion TEXT NULL":
                ownership_at_creation.append(self.saved.payload["description_created"])

        self.cursor.execute.side_effect = execute
        with patch.object(self.migration, "review", return_value=self.definition), patch.object(
            self.migration.helpers, "recreate"
        ):
            self.migration.install(self.apps, self.editor)
        self.assertEqual(ownership_at_creation, [False])
        self.assertIs(self.saved.payload["description_created"], True)
        self.saved.save.assert_called_once_with(using="isolated", update_fields=["payload"])
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertEqual(statements.count("ALTER TABLE actividad ADD COLUMN descripcion TEXT NULL"), 1)

    def test_failed_column_creation_never_marks_preexisting_column_as_owned(self):
        self.cursor.fetchone.side_effect = [None, ("utf8mb4", "utf8mb4_unicode_ci")]

        def execute(statement, *args):
            if statement == "ALTER TABLE actividad ADD COLUMN descripcion TEXT NULL":
                raise RuntimeError("synthetic concurrent column creation")

        self.cursor.execute.side_effect = execute
        with patch.object(self.migration, "review", return_value=self.definition), patch.object(
            self.migration.helpers, "recreate"
        ) as recreate, self.assertRaisesRegex(RuntimeError, "synthetic"):
            self.migration.install(self.apps, self.editor)
        self.assertIs(self.saved.payload["description_created"], False)
        self.saved.save.assert_not_called()
        recreate.assert_not_called()

    def test_invalid_state_collation_still_blocks_installation(self):
        self.cursor.fetchone.side_effect = [self.compatible_column, ("utf8mb4", "invalid;identifier")]
        with patch.object(self.migration, "review", return_value=self.definition), self.assertRaisesRegex(
            RuntimeError, "collation"
        ):
            self.migration.install(self.apps, self.editor)
        self.backups.create.assert_not_called()
        self.assertTrue(all(call.args[0].startswith("SELECT ") for call in self.cursor.execute.call_args_list))

    def test_reverse_preserves_preexisting_description_without_reading_or_modifying_data(self):
        self.cursor.fetchone.side_effect = [(0,)]
        with patch.object(self.migration, "review") as review, patch.object(
            self.migration.helpers, "recreate"
        ) as recreate:
            self.migration.restore(self.apps, self.editor)
        self.cursor.execute.assert_called_once_with("SELECT EXISTS(SELECT 1 FROM proyecto_estado_actividad)")
        review.assert_called_once_with(self.cursor, updated=True)
        recreate.assert_called_once_with(
            self.cursor, self.migration.PROCEDURE, self.definition["Create Procedure"], self.restored.payload
        )
        self.restored.delete.assert_called_once()

    def test_reverse_still_blocks_used_states_when_description_is_preexisting(self):
        self.cursor.fetchone.side_effect = [(1,)]
        with patch.object(self.migration.helpers, "recreate") as recreate, self.assertRaisesRegex(
            RuntimeError, "Project states are in use"
        ):
            self.migration.restore(self.apps, self.editor)
        self.cursor.execute.assert_called_once_with("SELECT EXISTS(SELECT 1 FROM proyecto_estado_actividad)")
        recreate.assert_not_called()
        self.restored.delete.assert_not_called()

    def test_reverse_without_valid_ownership_refuses_any_schema_change(self):
        for marker in (None, "true", 0, 1):
            with self.subTest(marker=marker):
                self.restored.payload = {**self.definition, "description_created": marker}
                with self.assertRaisesRegex(RuntimeError, "ownership"):
                    self.migration.restore(self.apps, self.editor)
                self.cursor.execute.assert_not_called()
                self.restored.delete.assert_not_called()

    def test_reverse_rejects_missing_or_incompatible_owned_column_before_ddl(self):
        self.restored.payload["description_created"] = True
        for column in (None, ("text", "text", "NO", None, "", "")):
            with self.subTest(column=column), patch.object(self.migration.helpers, "recreate") as recreate:
                self.cursor.reset_mock()
                self.cursor.fetchone.side_effect = [column]
                with self.assertRaises(RuntimeError):
                    self.migration.restore(self.apps, self.editor)
                self.assertEqual(self.cursor.execute.call_count, 1)
                self.assertTrue(self.cursor.execute.call_args.args[0].startswith("SELECT "))
                recreate.assert_not_called()
                self.restored.delete.assert_not_called()

    def test_changed_procedure_is_rejected_before_forward_or_reverse_ddl(self):
        with patch.object(self.migration.helpers, "read_definition", return_value={"Create Procedure": "BEGIN SELECT 1; END"}):
            for operation in (self.migration.preflight, self.migration.install, self.migration.restore):
                with self.subTest(operation=operation.__name__), self.assertRaisesRegex(RuntimeError, "reviewed baseline"):
                    self.cursor.reset_mock()
                    self.cursor.fetchone.side_effect = [(0,)]
                    operation(self.apps, self.editor)
                self.assertTrue(all(call.args[0].startswith("SELECT ") for call in self.cursor.execute.call_args_list))
                self.backups.create.assert_not_called()
                self.restored.delete.assert_not_called()
