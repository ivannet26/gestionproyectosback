import os
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.db import DatabaseError, connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from apps.authentication.models import MigrationBackup
from apps.projects.models import Project, ProjectTaskStatus, Task, TaskDependency
from apps.projects.services.audit import audit_actor
from apps.projects.services.projects import eligible_project_workers
from apps.workers.models import WorkerArea
from . import test_projects as fixtures


migration = import_module("apps.projects.migrations.0007_project_single_area")
SQL_ROOT = Path(__file__).resolve().parents[2]


def require_isolated_mysql():
    if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings_test_mysql":
        raise unittest.SkipTest("Requires explicit isolated MySQL settings")
    if connection.vendor != "mysql" or connection.settings_dict["HOST"] != "127.0.0.1":
        raise RuntimeError("Tests require isolated loopback MySQL")
    if connection.settings_dict["NAME"] != "gm_test_single_area":
        raise RuntimeError("Tests require dedicated synthetic database")
    if connection.introspection.table_names():
        raise RuntimeError("MySQL fixture database must be empty; existing data will not be removed")


class ProjectSingleAreaMySQLTests(unittest.TestCase):
    account = fixtures.ProjectFlowTests.account
    request = fixtures.ProjectFlowTests.request
    project_payload = fixtures.ProjectFlowTests.project_payload
    project = fixtures.ProjectFlowTests.project
    assigned_project = fixtures.ProjectFlowTests.assigned_project
    task_payload = fixtures.ProjectFlowTests.task_payload
    task = fixtures.ProjectFlowTests.task

    @classmethod
    def setUpClass(cls):
        require_isolated_mysql()
        cls.tables = [apps.get_model(label) for label in (
            "organization.Area", "workers.Worker", "workers.WorkerArea", "teams.Team", "teams.TeamMember","autenticacion.User",
            "autenticacion.Role", "autenticacion.UserRole", "autenticacion.AuthToken", "proyectos.ProjectType",
            "proyectos.ProjectState", "proyectos.TaskState", "proyectos.TaskTransition", "proyectos.Project",
            "proyectos.ProjectFavorite", "proyectos.ProjectMember", "proyectos.ProjectRequirement", "proyectos.ProjectTaskStatus",
            "proyectos.Task", "proyectos.TaskAssignee", "proyectos.TaskDependency", "proyectos.TaskLabel", "proyectos.TaskRelation", "proyectos.TaskActivity", "autenticacion.MigrationBackup",
        )]
        with connection.schema_editor() as editor:
            for model in cls.tables:
                editor.create_model(model)
        MigrationRecorder(connection).ensure_schema()
        with connection.cursor() as cursor:
            cursor.execute(
                (SQL_ROOT / "authentication/migrations/sql/v_trabajador_area_autorizada.sql").read_text(
                    encoding="utf-8"
                )
            )
            cursor.execute(
                "CREATE TABLE test_entregable (actividad_id BIGINT NOT NULL, obligatorio BOOLEAN NOT NULL, estado_revision VARCHAR(30) NOT NULL)"
            )
            cursor.execute("CREATE SQL SECURITY INVOKER VIEW v_estado_entregable AS SELECT * FROM test_entregable")
        cls.state = MigrationLoader(None).project_state([("proyectos", "0006_task_descriptions_and_project_states")])

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute(f"DROP PROCEDURE IF EXISTS {migration.PROCEDURE}")
            cursor.execute("DROP VIEW v_estado_entregable")
            cursor.execute("DROP VIEW v_trabajador_area_autorizada")
            cursor.execute("DROP TABLE test_entregable")
            cursor.execute("DROP TABLE IF EXISTS proyecto_area")
            cursor.execute("DROP TABLE django_migrations")
        with connection.schema_editor() as editor:
            for model in reversed(cls.tables):
                editor.delete_model(model)

    def setUp(self):
        fixtures.ProjectFlowTests.setUp(self)
        self.maintenance = patch.dict(os.environ, {"PROJECT_AREA_MIGRATION_MAINTENANCE": "1"})
        self.maintenance.start()
        self.addCleanup(self.maintenance.stop)
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE proyecto_area (area_id BIGINT NOT NULL, proyecto_id BIGINT NOT NULL, PRIMARY KEY(proyecto_id,area_id), CONSTRAINT fk_pa_project FOREIGN KEY(proyecto_id) REFERENCES proyecto(id), CONSTRAINT fk_pa_area FOREIGN KEY(area_id) REFERENCES area(id))"
            )
            migration.helpers.recreate(cursor, migration.PROCEDURE, migration.source(False))

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS proyecto_area")
            cursor.execute("DELETE FROM test_entregable")
            cursor.execute("DELETE FROM django_migrations")
            for model in reversed(self.tables):
                cursor.execute(f"DELETE FROM `{model._meta.db_table}`")

    def associate(self, project, area=None):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO proyecto_area(proyecto_id,area_id) VALUES(%s,%s)", [project.pk, (area or self.area).pk]
            )

    def apply(self):
        instance = migration.Migration("0007_project_single_area", "proyectos")
        return MigrationExecutor(connection).apply_migration(self.state.clone(), instance)

    def call_state(self, user, project, task, target="EN_CURSO", reason=None):
        with audit_actor(user), connection.cursor() as cursor:
            cursor.callproc(migration.PROCEDURE, [project.pk, task.pk, target, reason])
            while cursor.nextset():
                pass
        task.refresh_from_db()

    def assert_preflight_preserved(self, project):
        self.assertIn("proyecto_area", connection.introspection.table_names())
        self.assertFalse(MigrationBackup.objects.exists())
        with connection.cursor() as cursor:
            migration.review_procedure(cursor)
        project.refresh_from_db()
        self.assertEqual(project.area_id, self.area.pk)

    def test_migration_retires_table_after_procedure_and_preserves_data(self):
        project = self.project(
            mode="assigned", worker_ids=[self.worker.worker_id], worker_contribute=True, end_date=None
        )
        self.associate(project)
        task = self.task(project, responsible_id=self.worker.worker_id)
        WorkerArea.objects.create(worker=self.worker.worker, area=self.area)
        WorkerArea.objects.create(worker=self.worker.worker, area=self.other_area)
        state = self.apply()
        with self.assertRaises(LookupError):
            state.apps.get_model("proyectos", "ProjectArea")
        self.assertNotIn("proyecto_area", connection.introspection.table_names())
        self.assertEqual(WorkerArea.objects.filter(worker=self.worker.worker).count(), 2)
        task.refresh_from_db()
        project.refresh_from_db()
        self.assertEqual(project.area_id, self.area.pk)
        self.assertIsNone(project.end_date)
        self.assertEqual(task.state_code, "PENDIENTE")
        backup = MigrationBackup.objects.get(key=migration.BACKUP_KEY)
        self.assertEqual(backup.payload["phase"], "table_removed")
        self.assertIn("CREATE TABLE", backup.payload["table"])
        response = self.request("post", f"{project.pk}/tasks/{task.pk}/state/", {"state_code": "EN_CURSO"}, self.worker)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state_code"], "EN_CURSO")
        queries = (migration.SQL_DIR / "verify_project_single_area.0007.sql").read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            for statement in queries.split(";"):
                if statement.strip():
                    cursor.execute(statement)
                    cursor.fetchall()
        self.assertIn(("proyectos", "0007_project_single_area"), MigrationRecorder(connection).applied_migrations())
        with connection.schema_editor(atomic=False) as editor:
            migration.install(self.state.apps, editor)

    def test_inconsistent_history_blocks_before_any_change(self):
        for case in ("missing", "multiple", "different"):
            with self.subTest(case=case):
                project = self.project()
                if case != "missing":
                    self.associate(project, self.other_area)
                if case == "multiple":
                    self.associate(project)
                with self.assertRaisesRegex(RuntimeError, "inconsistencies") as error:
                    self.apply()
                self.assertIn(str(project.pk), str(error.exception))
                self.assertIn(project.code, str(error.exception))
                self.assert_preflight_preserved(project)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM proyecto_area WHERE proyecto_id=%s", [project.pk])
                    self.assertEqual(cursor.fetchone()[0], {"missing": 0, "multiple": 2, "different": 1}[case])
                    cursor.execute("DELETE FROM proyecto_area WHERE proyecto_id=%s", [project.pk])
                project.delete()

    def test_unreviewed_dependencies_block_retirement(self):
        project = self.project()
        self.associate(project)
        definitions = (
            ("VIEW", "test_pa_view", "CREATE VIEW test_pa_view AS SELECT * FROM proyecto_area"),
            ("PROCEDURE", "test_pa_proc", "CREATE PROCEDURE test_pa_proc() SELECT * FROM proyecto_area"),
            (
                "TRIGGER",
                "test_pa_trigger",
                "CREATE TRIGGER test_pa_trigger BEFORE INSERT ON proyecto_area FOR EACH ROW SET NEW.area_id=NEW.area_id",
            ),
            (
                "EVENT",
                "test_pa_event",
                "CREATE EVENT test_pa_event ON SCHEDULE EVERY 1 DAY DISABLE DO DELETE FROM proyecto_area WHERE 1=0",
            ),
        )
        for kind, name, sql in definitions:
            with self.subTest(kind=kind), connection.cursor() as cursor:
                cursor.execute(sql)
                try:
                    with self.assertRaisesRegex(RuntimeError, "dependency|Triggers"):
                        self.apply()
                    self.assert_preflight_preserved(project)
                finally:
                    cursor.execute(f"DROP {kind} {name}")

    def test_modified_procedure_security_or_body_blocks_retirement(self):
        project = self.project()
        self.associate(project)
        for sql in (
            migration.source(False).replace("SQL SECURITY INVOKER", "SQL SECURITY DEFINER"),
            migration.source(False).replace("START TRANSACTION;", "START TRANSACTION; SET @unexpected=1;"),
        ):
            with connection.cursor() as cursor:
                migration.helpers.recreate(cursor, migration.PROCEDURE, sql)
            with self.assertRaisesRegex(RuntimeError, "baseline"):
                self.apply()
            self.assertIn("proyecto_area", connection.introspection.table_names())
            self.assertFalse(MigrationBackup.objects.exists())

    def test_creation_visibility_assignment_and_multi_area_workers(self):
        self.apply()
        WorkerArea.objects.create(worker=self.outsider.worker, area=self.area)
        WorkerArea.objects.create(worker=self.outsider.worker, area=self.other_area)
        for selected in (self.area, self.other_area):
            project = self.project(
                area_ids=[selected.pk], mode="assigned", worker_ids=[self.outsider.worker_id], end_date=None
            )
            self.assertEqual(project.area_id, selected.pk)
            self.assertEqual(self.request("get", f"{project.pk}/", user=self.outsider).status_code, 200)
            self.assertEqual(
                set(eligible_project_workers(project).values_list("pk", flat=True)) & {self.outsider.worker_id},
                {self.outsider.worker_id},
            )
        available = self.project()
        self.assertEqual(self.request("get", f"{available.pk}/", user=self.worker).status_code, 200)
        WorkerArea.objects.filter(worker=self.outsider.worker, area=self.area).delete()
        self.assertEqual(self.request("get", f"{available.pk}/", user=self.outsider).status_code, 404)
        self.assertEqual(self.request("post", data=self.project_payload(), user=self.worker).status_code, 403)
        for areas in ([], [self.area.pk, self.other_area.pk]):
            self.assertEqual(
                self.request("post", data=self.project_payload(area_ids=areas), user=self.admin).status_code, 400
            )
        self.assertNotIn("proyecto_area", connection.introspection.table_names())

    def test_sql_area_check_uses_project_and_preserves_worker_multiple_areas(self):
        self.apply()
        project = self.assigned_project(worker_contribute=True)
        task = self.task(project, responsible_id=self.worker.worker_id)
        WorkerArea.objects.create(worker=self.worker.worker, area=self.other_area)
        with self.assertRaisesRegex(DatabaseError, "area y permiso"):
            self.call_state(self.worker, project, task)
        WorkerArea.objects.create(worker=self.worker.worker, area=self.area)
        self.call_state(self.worker, project, task)
        self.assertEqual(task.state_code, "EN_CURSO")
        self.assertEqual(WorkerArea.objects.filter(worker=self.worker.worker).count(), 2)

    def test_sql_other_protections_remain_enforced(self):
        self.apply()
        project = self.assigned_project(worker_contribute=True)
        for change, restore in (
            ({"worker_state": False}, {"worker_state": True}),
            ({"state_code": "FINALIZADO"}, {"state_code": "PLANIFICADO"}),
        ):
            task = self.task(project, responsible_id=self.worker.worker_id)
            Project.objects.filter(pk=project.pk).update(**change)
            with self.assertRaises(DatabaseError):
                self.call_state(self.worker, project, task)
            Project.objects.filter(pk=project.pk).update(**restore)
            task.refresh_from_db()
            self.assertEqual(task.state_code, "PENDIENTE")
        task = self.task(project, responsible_id=self.worker.worker_id)
        with self.assertRaisesRegex(DatabaseError, "motivo"):
            self.call_state(self.worker, project, task, "BLOQUEADA")
        with self.assertRaisesRegex(DatabaseError, "permiso"):
            self.call_state(self.worker, project, task, "CANCELADA", "Prueba")
        ProjectTaskStatus.objects.create(project=project, code="PENDIENTE", name="Pendiente", position=0)
        with self.assertRaisesRegex(DatabaseError, "no habilitado"):
            self.call_state(self.admin, project, task)
        ProjectTaskStatus.objects.filter(project=project).delete()
        predecessor = self.task(project, responsible_id=self.worker.worker_id)
        TaskDependency.objects.create(project=project, predecessor=predecessor, successor=task)
        with self.assertRaisesRegex(DatabaseError, "predecesoras"):
            self.call_state(self.admin, project, task)
        TaskDependency.objects.all().delete()
        parent = self.task(project, responsible_id=self.worker.worker_id)
        Task.objects.filter(pk=task.pk).update(parent=parent)
        Task.objects.filter(pk=parent.pk).update(state_code="COMPLETADA")
        with self.assertRaisesRegex(DatabaseError, "padre"):
            self.call_state(self.admin, project, task)
        Task.objects.filter(pk=parent.pk).update(state_code="EN_REVISION")
        with self.assertRaisesRegex(DatabaseError, "subtareas"):
            self.call_state(self.admin, project, parent, "COMPLETADA")
        Task.objects.filter(pk=task.pk).update(parent=None, state_code="EN_REVISION")
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO test_entregable VALUES(%s,1,'PENDIENTE')", [task.pk])
        with self.assertRaisesRegex(DatabaseError, "entregables"):
            self.call_state(self.admin, project, task, "COMPLETADA")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE test_entregable SET estado_revision='APROBADO'")
        self.call_state(self.admin, project, task, "COMPLETADA")
        self.assertEqual(task.state_code, "COMPLETADA")

    def test_maintenance_required_and_reverse_refuses_implicit_reconstruction(self):
        with patch.dict(os.environ, {"PROJECT_AREA_MIGRATION_MAINTENANCE": "0"}):
            with self.assertRaisesRegex(RuntimeError, "writers"):
                self.apply()
        self.apply()
        instance = migration.Migration("0007_project_single_area", "proyectos")
        with connection.schema_editor(atomic=False) as editor:
            with self.assertRaises(IrreversibleError):
                instance.unapply(self.state.clone(), editor)
        self.assertNotIn("proyecto_area", connection.introspection.table_names())

    def test_failed_procedure_install_restores_original_and_retains_table(self):
        project = self.project()
        self.associate(project)
        original = migration.helpers.recreate

        def fail_updated(cursor, name, definition, metadata=None):
            if definition == migration.source():
                cursor.execute(f"DROP PROCEDURE {name}")
                raise DatabaseError("synthetic CREATE failure")
            return original(cursor, name, definition, metadata)

        with patch.object(migration.helpers, "recreate", side_effect=fail_updated):
            with self.assertRaisesRegex(DatabaseError, "synthetic"):
                self.apply()
        self.assertIn("proyecto_area", connection.introspection.table_names())
        with connection.cursor() as cursor:
            migration.review_procedure(cursor)
        self.assertEqual(MigrationBackup.objects.get(key=migration.BACKUP_KEY).payload["phase"], "reviewed")
        self.apply()
        self.assertNotIn("proyecto_area", connection.introspection.table_names())

    def test_interruption_after_procedure_update_can_resume_without_data_repair(self):
        project = self.project()
        self.associate(project)
        original = migration.review_data
        count = 0

        def fail_second_review(cursor):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("synthetic interruption")
            original(cursor)

        with patch.object(migration, "review_data", side_effect=fail_second_review):
            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                self.apply()
        with connection.cursor() as cursor:
            self.assertTrue(migration.table_exists(cursor))
            migration.review_procedure(cursor, updated=True)
        self.apply()
        self.assertNotIn("proyecto_area", connection.introspection.table_names())
        project.refresh_from_db()
        self.assertEqual(project.area_id, self.area.pk)

    def test_orphan_extra_columns_and_inbound_keys_block_retirement(self):
        project = self.project()
        self.associate(project)
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE proyecto_area ADD COLUMN extra_data TEXT NULL")
            with self.assertRaisesRegex(RuntimeError, "columns"):
                self.apply()
            cursor.execute("ALTER TABLE proyecto_area DROP COLUMN extra_data")
            cursor.execute(
                "CREATE TABLE test_pa_child (proyecto_id BIGINT NOT NULL, area_id BIGINT NOT NULL, FOREIGN KEY(proyecto_id,area_id) REFERENCES proyecto_area(proyecto_id,area_id))"
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "Foreign keys"):
                    self.apply()
            finally:
                cursor.execute("DROP TABLE test_pa_child")
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            try:
                cursor.execute("INSERT INTO proyecto_area VALUES(999999,999999)")
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            with self.assertRaisesRegex(RuntimeError, "Orphan"):
                self.apply()
        self.assert_preflight_preserved(project)

    def test_absent_table_without_checkpoint_is_not_accepted(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE proyecto_area")
        with self.assertRaisesRegex(RuntimeError, "missing without"):
            self.apply()
        self.assertFalse(MigrationBackup.objects.exists())

    def test_assignments_reject_workers_outside_project_area_after_retirement(self):
        self.apply()
        response = self.request(
            "post", data=self.project_payload(mode="assigned", worker_ids=[self.outsider.worker_id]), user=self.admin
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Project.objects.exists())
        project = self.assigned_project(worker_contribute=True)
        response = self.request(
            "post", f"{project.pk}/tasks/", self.task_payload(responsible_id=self.outsider.worker_id), self.admin
        )
        self.assertEqual(response.status_code, 400, response.content)
        task = self.task(project, responsible_id=self.worker.worker_id)
        self.worker.is_active = False
        self.worker.save(update_fields=["is_active"])
        with self.assertRaises(DatabaseError):
            self.call_state(self.worker, project, task)


class ProjectSingleAreaReferenceMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_isolated_mysql()
        fixture = Path(__file__).with_name("project_single_area_reference.sql")
        cls.definitions = [sql.strip() for sql in fixture.read_text(encoding="utf-8").split(";") if sql.strip()]
        cls.tables = ("area", "cliente", "tipo_proyecto", "estado_proyecto", "proyecto")
        with connection.cursor() as cursor:
            for definition in cls.definitions[:-1]:
                cursor.execute(definition)
        with connection.schema_editor() as editor:
            editor.create_model(MigrationBackup)
        MigrationRecorder(connection).ensure_schema()
        cls.state = MigrationLoader(None).project_state([("proyectos", "0006_task_descriptions_and_project_states")])

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute(f"DROP PROCEDURE IF EXISTS {migration.PROCEDURE}")
            cursor.execute("DROP TABLE IF EXISTS proyecto_area")
            cursor.execute("DROP TABLE django_migrations")
            cursor.execute("DROP TABLE auth_migration_backup")
            for table in reversed(cls.tables):
                cursor.execute(f"DROP TABLE `{table}`")

    def setUp(self):
        self.maintenance = patch.dict(os.environ, {"PROJECT_AREA_MIGRATION_MAINTENANCE": "1"})
        self.maintenance.start()
        self.addCleanup(self.maintenance.stop)
        with connection.cursor() as cursor:
            cursor.execute(self.definitions[-1])
            cursor.execute("INSERT INTO area(id,codigo,nombre) VALUES(7,'SYNTHETIC','Área de prueba')")
            cursor.execute("INSERT INTO tipo_proyecto(codigo,nombre) VALUES('GENERAL','General')")
            cursor.execute("INSERT INTO estado_proyecto(codigo,nombre) VALUES('PLANIFICADO','Planificado')")
            cursor.execute(
                "INSERT INTO proyecto(id,codigo,nombre,area_id,tipo_codigo,estado_codigo,fecha_inicio,fecha_fin) "
                "VALUES(91,'SYNTHETIC-91','Proyecto de prueba',7,'GENERAL','PLANIFICADO','2026-10-10',NULL)"
            )
            cursor.execute("INSERT INTO proyecto_area(area_id,proyecto_id) VALUES(7,91)")
            migration.helpers.recreate(cursor, migration.PROCEDURE, migration.source(False))

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS proyecto_area")
            cursor.execute("DELETE FROM django_migrations")
            cursor.execute("DELETE FROM auth_migration_backup")
            for table in reversed(self.tables):
                cursor.execute(f"DELETE FROM `{table}`")

    def apply(self):
        instance = migration.Migration("0007_project_single_area", "proyectos")
        return MigrationExecutor(connection).apply_migration(self.state.clone(), instance)

    def assert_retirement(self):
        state = self.apply()
        with self.assertRaises(LookupError):
            state.apps.get_model("proyectos", "ProjectArea")
        self.assertNotIn("proyecto_area", connection.introspection.table_names())
        project = Project.objects.get(pk=91)
        self.assertEqual(project.area_id, 7)
        self.assertIsNone(project.end_date)
        self.assertIn(("proyectos", "0007_project_single_area"), MigrationRecorder(connection).applied_migrations())
        with connection.cursor() as cursor:
            migration.review_procedure(cursor, updated=True)

    def test_reference_order_unsigned_keys_and_nullable_end_allow_migration(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto_area' ORDER BY ORDINAL_POSITION"
            )
            self.assertEqual(
                cursor.fetchall(), (("area_id", "bigint unsigned", "NO"), ("proyecto_id", "bigint unsigned", "NO"))
            )
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto_area' "
                "AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION"
            )
            self.assertEqual(cursor.fetchall(), (("proyecto_id",), ("area_id",)))
        self.assert_retirement()
        saved = MigrationBackup.objects.get(key=migration.BACKUP_KEY)
        self.assertIn("fk_proyecto_area_area", saved.payload["table"])
        self.assertIn("fk_proyecto_area_proyecto", saved.payload["table"])

    def test_legacy_physical_column_order_also_allows_migration(self):
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE proyecto_area MODIFY proyecto_id BIGINT UNSIGNED NOT NULL FIRST")
        self.assert_retirement()

    def assert_columns_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "columns"):
            self.apply()
        self.assertIn("proyecto_area", connection.introspection.table_names())
        self.assertFalse(MigrationBackup.objects.exists())
        self.assertFalse(MigrationRecorder(connection).applied_migrations())
        with connection.cursor() as cursor:
            migration.review_procedure(cursor)
        self.assertEqual(Project.objects.get(pk=91).area_id, 7)

    def test_additional_column_blocks_before_sql_changes(self):
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE proyecto_area ADD COLUMN extra_data TEXT NULL")
        self.assert_columns_rejected()

    def test_missing_column_blocks_before_sql_changes(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE proyecto_area")
            cursor.execute("CREATE TABLE proyecto_area(proyecto_id BIGINT UNSIGNED NOT NULL)")
            cursor.execute("INSERT INTO proyecto_area(proyecto_id) VALUES(91)")
        self.assert_columns_rejected()
