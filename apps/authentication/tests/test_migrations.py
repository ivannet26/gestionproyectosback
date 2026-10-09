from importlib import import_module
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import SimpleTestCase

from apps.organization.models import Area
from apps.workers.models import Worker, WorkerArea

from apps.authentication.models import MigrationBackup, Role, User, UserRole


scope_migration = import_module("apps.authentication.migrations.0002_worker_areas_invitations")
roles_migration = import_module("apps.authentication.migrations.0003_final_roles_and_existing_areas")
policy_migration = import_module("apps.authentication.migrations.0004_global_admin_sql_policy")
SQL_DIR = Path(policy_migration.__file__).parent / "sql"


class RoleDataMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("AUTH_TEST_SQLITE") != "1" or connection.vendor != "sqlite":
            raise unittest.SkipTest("Data migration tests require isolated SQLite")
        cls.tables = [Area, Worker, WorkerArea, User, Role, UserRole, MigrationBackup]
        with connection.schema_editor() as editor:
            for model in cls.tables:
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(cls.tables):
                editor.delete_model(model)

    def setUp(self):
        self.editor = SimpleNamespace(connection=connection)
        self.area = Area.objects.create(code="SYN", name="Área sintética", active=True)
        self.catalog = [
            ("ADMINISTRADOR", "Administrador de cuentas"),
            ("COLABORADOR", "Trabajador"),
            ("COORDINADOR", "Coordinador"),
            ("GERENCIA", "Gerencia"),
            ("REVISOR", "Revisor"),
        ]
        for code, name in self.catalog:
            Role.objects.create(code=code, name=name)
        self.admin = self.account("ADM", "ADMINISTRADOR")
        self.worker = self.account("WORK", "COLABORADOR")

    def tearDown(self):
        with connection.cursor() as cursor:
            for model in reversed(self.tables):
                cursor.execute(f'DELETE FROM "{model._meta.db_table}"')

    def account(self, code, role):
        worker = Worker.objects.create(
            area=self.area,
            code=code,
            first_names="Sintético",
            last_names=code,
            email=f"{code.lower()}@example.com",
            active=True,
        )
        user = User.objects.create(worker=worker, username=f"gm_{code}", password=make_password(None), is_active=True)
        UserRole.objects.create(user=user, role_code=role)
        return user

    def test_forward_and_reverse_preserve_admin_identity_and_primary_areas(self):
        before_admin = User.objects.values().get(pk=self.admin.pk)
        before_worker = User.objects.values().get(pk=self.worker.pk)
        roles_migration.transition(apps, self.editor)
        self.assertEqual(set(Role.objects.values_list("code", flat=True)), {"ADMINISTRADOR", "TRABAJADOR"})
        self.assertEqual(Role.objects.get(pk="ADMINISTRADOR").name, "Administrador de cuentas")
        self.assertEqual(self.admin.global_role, "ADMINISTRADOR")
        self.assertEqual(self.worker.global_role, "TRABAJADOR")
        self.assertEqual(User.objects.values().get(pk=self.admin.pk), before_admin)
        self.assertEqual(User.objects.values().get(pk=self.worker.pk), before_worker)
        self.assertEqual(WorkerArea.objects.count(), 2)
        self.assertTrue(WorkerArea.objects.filter(worker=self.worker.worker, area=self.area).exists())
        roles_migration.restore(apps, self.editor)
        self.assertEqual(set(Role.objects.values_list("code", "name")), set(self.catalog))
        self.assertEqual(
            set(UserRole.objects.values_list("user_id", "role_code")),
            {(self.admin.pk, "ADMINISTRADOR"), (self.worker.pk, "COLABORADOR")},
        )
        self.assertFalse(WorkerArea.objects.exists())
        self.assertFalse(MigrationBackup.objects.exists())
        self.assertEqual(Worker.objects.get(pk=self.worker.worker_id).area_id, self.area.pk)

    def test_existing_canonical_role_and_area_relationships_are_restored(self):
        Role.objects.create(code="TRABAJADOR", name="Personal registrado")
        UserRole.objects.create(user=self.worker, role_code="TRABAJADOR")
        UserRole.objects.create(user=self.admin, role_code="COLABORADOR")
        WorkerArea.objects.create(worker=self.worker.worker, area=self.area)
        roles_migration.transition(apps, self.editor)
        self.assertEqual(self.admin.global_role, "ADMINISTRADOR")
        self.assertEqual(self.worker.global_role, "TRABAJADOR")
        roles_migration.restore(apps, self.editor)
        self.assertEqual(Role.objects.get(pk="TRABAJADOR").name, "Personal registrado")
        self.assertTrue(UserRole.objects.filter(user=self.admin, role_code="COLABORADOR").exists())
        self.assertTrue(UserRole.objects.filter(user=self.worker, role_code="TRABAJADOR").exists())
        self.assertEqual(WorkerArea.objects.count(), 1)

    def test_unexpected_global_assignments_stop_without_changes(self):
        for legacy_role in ("COORDINADOR", "GERENCIA", "REVISOR"):
            with self.subTest(role=legacy_role):
                assignment = UserRole.objects.create(user=self.worker, role_code=legacy_role)
                with self.assertRaises(RuntimeError):
                    roles_migration.transition(apps, self.editor)
                self.assertFalse(MigrationBackup.objects.exists())
                self.assertEqual(Role.objects.count(), 5)
                self.assertTrue(UserRole.objects.filter(user=self.worker, role_code=legacy_role).exists())
                assignment.delete()

    def test_rollback_stops_if_new_accounts_depend_on_worker_role(self):
        roles_migration.transition(apps, self.editor)
        self.account("NEW", "TRABAJADOR")
        with self.assertRaises(RuntimeError):
            roles_migration.restore(apps, self.editor)
        self.assertEqual(set(Role.objects.values_list("code", flat=True)), {"ADMINISTRADOR", "TRABAJADOR"})
        self.assertTrue(MigrationBackup.objects.exists())

    def test_rollback_stops_if_existing_account_permissions_changed(self):
        roles_migration.transition(apps, self.editor)
        UserRole.objects.filter(user=self.worker).update(role_code="ADMINISTRADOR")
        with self.assertRaises(RuntimeError):
            roles_migration.restore(apps, self.editor)
        self.assertTrue(MigrationBackup.objects.exists())


class MigrationDefinitionTests(SimpleTestCase):
    def mysql_editor(self, *results):
        editor = MagicMock()
        editor.connection.vendor = "mysql"
        cursor = editor.connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = results
        return editor

    def test_scope_ddl_preserves_primary_fk_and_unsigned_type(self):
        editor = self.mysql_editor(("bigint unsigned", "NO"), (0,))
        scope_migration.extend_worker(apps, editor)
        sql = editor.execute.call_args.args[0]
        self.assertIn("MODIFY area_id BIGINT UNSIGNED NULL", sql)
        self.assertIn("todas_las_areas = 1 AND area_id IS NULL", sql)
        self.assertIn("todas_las_areas = 0 AND area_id IS NOT NULL", sql)
        self.assertNotIn("DROP FOREIGN KEY", sql)
        self.assertNotIn("UPDATE trabajador", sql)

    def test_scope_ddl_rejects_schema_drift_and_unexpected_roles(self):
        for editor in (self.mysql_editor(("bigint", "NO")), self.mysql_editor(("bigint unsigned", "NO"), (1,))):
            with self.assertRaises(RuntimeError):
                scope_migration.extend_worker(apps, editor)
            editor.execute.assert_not_called()

    def test_rollback_guards_all_and_multiple_areas(self):
        for results in (((1,),), ((0,), (1,)), ((0,), (0,), (1,))):
            with self.assertRaises(RuntimeError):
                scope_migration.guard_rollback(apps, self.mysql_editor(*results))

    def test_final_catalog_constraint_rejects_other_global_codes(self):
        editor = self.mysql_editor()
        roles_migration.enforce_final_catalog(apps, editor)
        self.assertEqual(
            editor.execute.call_args.args[0],
            "ALTER TABLE rol ADD CONSTRAINT ck_rol_global CHECK (codigo IN ('ADMINISTRADOR', 'TRABAJADOR'))",
        )

    def test_supervisor_policy_gives_admin_an_independent_global_branch(self):
        sql = (SQL_DIR / "sp_validar_supervisor.sql").read_text(encoding="utf-8")
        admin_branch, worker_branch = sql.split("  OR (", 1)
        self.assertIn("ur.rol_codigo='ADMINISTRADOR'", admin_branch)
        self.assertNotIn("proyecto_miembro", admin_branch)
        self.assertIn("ur.rol_codigo='TRABAJADOR'", worker_branch)
        self.assertIn("pm.rol_proyecto='RESPONSABLE'", worker_branch)
        self.assertIn("v_trabajador_area_autorizada", worker_branch)
        self.assertNotIn("COORDINADOR", sql)
        self.assertNotIn("GERENCIA", sql)

    def test_activity_policy_keeps_worker_assignment_and_business_rules(self):
        baseline = (SQL_DIR / "sp_cambiar_estado_actividad.before.sql").read_text(encoding="utf-8")
        desired = (SQL_DIR / "sp_cambiar_estado_actividad.sql").read_text(encoding="utf-8")
        self.assertIn("IF v_administrador=0 AND", desired)
        self.assertIn("SELECT (v_administrador=1 OR EXISTS", desired)
        self.assertIn("v_trabajador_area_autorizada", desired)
        unchanged = " IF NOT EXISTS(SELECT 1 FROM transicion_actividad"
        self.assertEqual(baseline[baseline.index(unchanged) :], desired[desired.index(unchanged) :])
        self.assertIn("v_supervision=0 AND NOT(v_responsable<=>v_persona)", desired)
        self.assertNotIn("COORDINADOR", desired)

    def test_all_areas_view_is_dynamic_and_does_not_multiply_availability(self):
        scope = (SQL_DIR / "v_trabajador_area_autorizada.sql").read_text(encoding="utf-8")
        availability = (SQL_DIR / "v_disponibilidad_actual.sql").read_text(encoding="utf-8")
        self.assertIn("JOIN area a ON a.activa=1", scope)
        self.assertIn("t.todas_las_areas=1", scope)
        self.assertIn("t.area_id=a.id", scope)
        self.assertIn("t.todas_las_areas", availability)
        self.assertNotIn("JOIN trabajador_area", availability)
