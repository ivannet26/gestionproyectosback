from datetime import timedelta
from importlib import import_module
import os
import unittest
from unittest.mock import patch

from django.apps import apps
from django.db import DatabaseError, connection

from apps.projects.models import Task
from . import test_quick_tasks as cases
from . import test_state_templates_mysql as fixtures


migration = import_module("apps.projects.migrations.0011_task_optional_properties")


class QuickTasksMySQLTests(unittest.TestCase):
    account = fixtures.StateTemplatesMySQLTests.account
    request = fixtures.StateTemplatesMySQLTests.request
    project_payload = fixtures.StateTemplatesMySQLTests.project_payload
    project = fixtures.StateTemplatesMySQLTests.project
    assigned_project = fixtures.StateTemplatesMySQLTests.assigned_project
    task_payload = fixtures.StateTemplatesMySQLTests.task_payload
    task = fixtures.StateTemplatesMySQLTests.task

    @classmethod
    def setUpClass(cls):
        fixtures.StateTemplatesMySQLTests.setUpClass.__func__(cls)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE fase (id BIGINT PRIMARY KEY, proyecto_id BIGINT NOT NULL, archivada BOOLEAN NOT NULL DEFAULT 0, fecha_inicio DATE NOT NULL, fecha_fin DATE NOT NULL)")
            cursor.execute("ALTER TABLE actividad MODIFY fecha_fin DATE NOT NULL, MODIFY prioridad SMALLINT UNSIGNED NOT NULL DEFAULT 3")
        with patch.dict(os.environ, {"TASK_OPTIONAL_MIGRATION_MAINTENANCE": "1"}), connection.schema_editor() as editor:
            migration.install(apps, editor)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER test_bi_actividad BEFORE INSERT ON actividad FOR EACH ROW "
                           "CALL sp_validar_estructura_actividad(NEW.id,NEW.proyecto_id,NEW.fase_id,NEW.padre_id,NEW.fecha_inicio,NEW.fecha_fin)")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute("DROP TRIGGER test_bi_actividad")
            cursor.execute("DROP TABLE fase")
        fixtures.StateTemplatesMySQLTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.StateTemplatesMySQLTests.setUp(self)
        self.fixture = self

    tearDown = fixtures.StateTemplatesMySQLTests.tearDown
    test_name_only = cases.QuickTaskTests.test_only_name_and_context_preserve_real_empty_values
    test_combinations = cases.QuickTaskTests.test_all_optional_combinations_use_the_same_endpoint
    test_patch_nulls = cases.QuickTaskTests.test_partial_omission_preserves_and_explicit_null_clears
    test_validation = cases.QuickTaskTests.test_supplied_values_and_required_name_stay_validated_atomically
    test_permissions = cases.QuickTaskTests.test_worker_ownership_and_revoked_permissions_are_unchanged
    test_parent_bounds = cases.QuickTaskTests.test_undated_parent_child_and_new_bounds_remain_consistent
    test_independent_permissions = cases.QuickTaskTests.test_effective_creation_and_state_permissions_are_independent

    def test_sql_null_to_date_is_checked_by_trigger(self):
        project = self.project()
        task = self.task(project, due_date=None, priority=None)
        with connection.cursor() as cursor:
            migration.review(cursor, migration.source())
            migration.trigger_review(cursor, installed=True)
            cursor.execute("SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='actividad' AND COLUMN_NAME IN ('fecha_fin','prioridad')")
            self.assertEqual([row[0] for row in cursor.fetchall()], ["YES", "YES"])
            with self.assertRaises(DatabaseError):
                cursor.execute("UPDATE actividad SET fecha_fin=%s WHERE id=%s", [self.today - timedelta(days=1), task.pk])
            with self.assertRaises(DatabaseError):
                cursor.execute("UPDATE actividad SET fecha_fin=%s WHERE id=%s", [project.end_date + timedelta(days=1), task.pk])
            cursor.execute("UPDATE actividad SET fecha_fin=%s WHERE id=%s", [self.today + timedelta(days=3), task.pk])
            cursor.execute("UPDATE actividad SET fecha_fin=NULL WHERE id=%s", [task.pk])
        task.refresh_from_db()
        self.assertIsNone(task.due_date)

    def test_migration_maintenance_and_rollback_preserve_nullable_data(self):
        task = self.task(self.project(), due_date=None, priority=None)
        with connection.schema_editor() as editor:
            with patch.dict(os.environ, {"TASK_OPTIONAL_MIGRATION_MAINTENANCE": "0"}), self.assertRaises(RuntimeError):
                migration.restore(apps, editor)
            with patch.dict(os.environ, {"TASK_OPTIONAL_MIGRATION_MAINTENANCE": "1"}):
                with self.assertRaises(RuntimeError):
                    migration.restore(apps, editor)
                task.due_date = self.today + timedelta(days=5)
                task.priority = 3
                task.save()
                migration.restore(apps, editor)
                with connection.cursor() as cursor:
                    migration.review(cursor, migration.baseline.source(migration.ROUTINE))
                    migration.trigger_review(cursor)
                migration.install(apps, editor)
