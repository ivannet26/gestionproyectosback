import ast
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import AppConfig, apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.urls import resolve

from apps.authentication import models as authentication_models
from apps.authentication.models import FINAL_ROLES, User
from apps.organization.models import Area, Specialty
from apps.projects.models import Project, ProjectArea, ProjectMember, Task
from apps.workers.models import Worker, WorkerArea, WorkerSpecialty


class CanonicalApplicationTests(SimpleTestCase):
    def test_active_domains_have_one_canonical_configuration(self):
        configured = list(apps.get_app_configs())
        for name, label in (
            ("authentication", "autenticacion"),
            ("projects", "proyectos"),
            ("organization", "organization"),
            ("workers", "workers"),
        ):
            with self.subTest(application=name):
                matches = [
                    configuration for configuration in configured
                    if configuration.name == f"apps.{name}"
                ]
                self.assertEqual(len(matches), 1)
                self.assertIs(apps.get_app_config(label), matches[0])
                declarations = [
                    entry for entry in settings.INSTALLED_APPS
                    if entry == f"apps.{name}"
                    or entry.startswith(f"apps.{name}.apps.")
                ]
                self.assertEqual(len(declarations), 1)

    def test_inactive_domains_remain_separate_and_are_not_enabled(self):
        configured = {configuration.name for configuration in apps.get_app_configs()}
        for name in (
            "activities", "administration", "audit",
            "deliverables", "teams", "tracking",
        ):
            with self.subTest(application=name):
                configuration = AppConfig.create(f"apps.{name}")
                self.assertEqual(configuration.name, f"apps.{name}")
                self.assertEqual(configuration.label, name)
                self.assertNotIn(configuration.name, configured)

    def test_retired_application_directories_are_absent(self):
        applications = settings.BASE_DIR / "apps"
        for name in (
            "actividades", "administracion", "auditoria", "autenticacion",
            "entregables", "proyectos", "equipos", "seguimiento",
        ):
            with self.subTest(application=name):
                self.assertFalse((applications / name).exists())
        self.assertFalse((settings.BASE_DIR / "authentication").exists())

    def test_every_physical_table_has_one_registered_model(self):
        owners = defaultdict(list)
        for model in apps.get_models(include_auto_created=True):
            if not model._meta.proxy:
                owners[model._meta.db_table].append(model._meta.label)
        for table, labels in owners.items():
            with self.subTest(table=table):
                self.assertEqual(len(labels), 1, labels)

    def test_runtime_sources_do_not_import_retired_application_packages(self):
        retired = (
            "actividades", "administracion", "auditoria", "autenticacion",
            "entregables", "proyectos", "equipos", "seguimiento",
        )
        prefixes = tuple(f"apps.{name}" for name in retired)
        sources = list((settings.BASE_DIR / "apps").rglob("*.py"))
        sources.extend((settings.BASE_DIR / "config").rglob("*.py"))
        for source in sources:
            tree = ast.parse(source.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                    if node.module == "apps":
                        names.extend(f"apps.{alias.name}" for alias in node.names)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    names = [node.value]
                for name in names:
                    with self.subTest(
                        source=str(source.relative_to(settings.BASE_DIR)),
                        line=node.lineno,
                    ):
                        self.assertFalse(
                            any(
                                name == prefix or name.startswith(f"{prefix}.")
                                for prefix in prefixes
                            ),
                            name,
                        )

    def test_migration_modules_follow_canonical_paths_with_historical_labels(self):
        loader = MigrationLoader(None)
        for label, path in (
            ("autenticacion", "apps.authentication.migrations"),
            ("proyectos", "apps.projects.migrations"),
            ("organization", "apps.organization.migrations"),
            ("workers", "apps.workers.migrations"),
        ):
            with self.subTest(application=label):
                self.assertEqual(loader.migrations_module(label)[0], path)
        self.assertEqual(settings.AUTH_USER_MODEL, "autenticacion.User")
        self.assertIs(get_user_model(), User)


class EntitySegmentationTests(SimpleTestCase):
    def test_entity_tables_have_one_runtime_owner(self):
        owners = {
            "area": Area,
            "especialidad": Specialty,
            "trabajador": Worker,
            "trabajador_area": WorkerArea,
            "trabajador_especialidad": WorkerSpecialty,
            "usuario": User,
            "proyecto": Project,
            "actividad": Task,
        }
        for table, owner in owners.items():
            with self.subTest(table=table):
                matches = [model for model in apps.get_models() if model._meta.db_table == table]
                self.assertEqual(matches, [owner])
        self.assertEqual(WorkerArea._meta.app_label, "workers")
        self.assertEqual(FINAL_ROLES, ("ADMINISTRADOR", "TRABAJADOR"))

    def test_authentication_does_not_export_organization_or_worker_models(self):
        for name in ("Area", "Worker", "WorkerArea"):
            self.assertFalse(hasattr(authentication_models, name))

    def test_related_models_use_the_entity_owner_and_original_columns(self):
        for model, field_name, owner, column in (
            (User, "worker", Worker, "trabajador_id"),
            (Worker, "area", Area, "area_id"),
            (WorkerArea, "worker", Worker, "trabajador_id"),
            (WorkerArea, "area", Area, "area_id"),
            (Project, "area", Area, "area_id"),
            (ProjectArea, "area", Area, "area_id"),
            (ProjectMember, "worker", Worker, "trabajador_id"),
            (Task, "responsible", Worker, "responsable_id"),
        ):
            with self.subTest(model=model.__name__, field=field_name):
                field = model._meta.get_field(field_name)
                self.assertIs(field.related_model, owner)
                self.assertEqual(field.column, column)
        self.assertEqual(WorkerArea._meta.pk.field_names, ("worker_id", "area_id"))

    def test_existing_routes_keep_their_contract_and_resolve_to_the_owner(self):
        for path, owner in (
            ("/api/auth/login/", "apps.authentication.views"),
            ("/api/auth/admin/invitations/", "apps.authentication.views"),
            ("/api/auth/admin/areas/", "apps.organization.views"),
            ("/api/organization/areas/", "apps.organization.views"),
            ("/api/organization/specialties/", "apps.organization.views"),
            ("/api/workers/", "apps.workers.views"),
            ("/api/projects/", "apps.projects.views"),
            ("/api/projects/7/tasks/11/dependencies/", "apps.projects.views"),
        ):
            with self.subTest(path=path):
                view = resolve(path).func
                self.assertEqual(view.cls.__module__, owner)

    def test_migration_dependency_graph_remains_acyclic(self):
        loader = MigrationLoader(None)
        loader.graph.validate_consistency()
        loader.graph.ensure_not_cyclic()

    def test_final_migration_state_uses_existing_entity_tables(self):
        registry = MigrationLoader(None).project_state().apps
        for table, label in (
            ("area", "organization.Area"),
            ("especialidad", "organization.Specialty"),
            ("trabajador", "workers.Worker"),
            ("trabajador_area", "workers.WorkerArea"),
            ("trabajador_especialidad", "workers.WorkerSpecialty"),
        ):
            with self.subTest(table=table):
                owners = [model._meta.label for model in registry.get_models() if model._meta.db_table == table]
                self.assertEqual(owners, [label])
        for app_label, model_name, field_name, owner in (
            ("autenticacion", "User", "worker", "workers.Worker"),
            ("proyectos", "ProjectArea", "area", "organization.Area"),
            ("workers", "WorkerArea", "worker", "workers.Worker"),
            ("workers", "WorkerArea", "area", "organization.Area"),
        ):
            model = registry.get_model(app_label, model_name)
            self.assertEqual(model._meta.get_field(field_name).related_model._meta.label, owner)
        relationship = registry.get_model("workers", "WorkerArea")
        self.assertEqual(relationship._meta.pk.field_names, ("worker_id", "area_id"))

    def test_pending_segmentation_migrations_have_no_database_operations(self):
        loader = MigrationLoader(None)
        for key in (
            ("organization", "0001_initial"),
            ("proyectos", "0004_organization_area_state"),
            ("autenticacion", "0005_alter_workerarea_area_delete_area"),
            ("workers", "0001_existing_worker_models"),
            ("autenticacion", "0006_alter_workerarea_worker_delete_worker"),
            ("autenticacion", "0007_worker_area_ownership"),
        ):
            with self.subTest(migration=key):
                operations = loader.disk_migrations[key].operations
                self.assertTrue(operations)
                for operation in operations:
                    self.assertIsInstance(operation, migrations.SeparateDatabaseAndState)
                    self.assertEqual(operation.database_operations, [])

    def test_reported_applied_history_remains_consistent(self):
        loader = MigrationLoader(None)
        applied = loader.graph.forwards_plan(("proyectos", "0003_project_sql_policy"))
        self.assertEqual(applied, [
            ("autenticacion", "0001_initial"),
            ("autenticacion", "0002_worker_areas_invitations"),
            ("autenticacion", "0003_final_roles_and_existing_areas"),
            ("autenticacion", "0004_global_admin_sql_policy"),
            ("proyectos", "0001_initial"),
            ("proyectos", "0002_project_schema"),
            ("proyectos", "0003_project_sql_policy"),
        ])
        with patch("django.db.migrations.loader.MigrationRecorder") as recorder:
            recorder.return_value.applied_migrations.return_value = dict.fromkeys(applied)
            loader.check_consistent_history(SimpleNamespace(alias="isolated-history"))

    def test_area_reference_is_transferred_before_old_model_is_removed(self):
        loader = MigrationLoader(None)
        plan = loader.graph.forwards_plan(("autenticacion", "0007_worker_area_ownership"))
        pending = [key for key in plan if key not in loader.graph.forwards_plan(("proyectos", "0003_project_sql_policy"))]
        self.assertEqual(pending, [
            ("organization", "0001_initial"),
            ("proyectos", "0004_organization_area_state"),
            ("autenticacion", "0005_alter_workerarea_area_delete_area"),
            ("workers", "0001_existing_worker_models"),
            ("autenticacion", "0006_alter_workerarea_worker_delete_worker"),
            ("autenticacion", "0007_worker_area_ownership"),
        ])
