import os
import unittest
from importlib import import_module
from unittest.mock import patch

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test.utils import CaptureQueriesContext

from apps.projects.models import Project, ProjectFavorite, ProjectMember
from apps.workers.models import WorkerArea
from . import test_projects as fixtures


class ProjectFavoriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProjectFlowTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.ProjectFlowTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.ProjectFlowTests()
        self.fixture.setUp()
        self.project = self.fixture.assigned_project()
        self.path = f"{self.project.pk}/favorite/"

    def tearDown(self):
        self.fixture.tearDown()

    def request(self, method, user=None, **kwargs):
        return self.fixture.request(method, self.path, user=user or self.fixture.admin, **kwargs)

    def detail(self, user):
        return self.fixture.request("get", f"{self.project.pk}/", user=user)

    def test_favorites_are_personal_persistent_and_idempotent(self):
        self.assertIs(self.detail(self.fixture.admin).json()["is_favorite"], False)
        for _ in range(2):
            self.assertEqual(self.request("put").json(), {"is_favorite": True})
        self.assertEqual(ProjectFavorite.objects.count(), 1)
        self.fixture.tokens.clear()
        self.assertIs(self.detail(self.fixture.admin).json()["is_favorite"], True)
        self.assertIs(self.detail(self.fixture.worker).json()["is_favorite"], False)
        response = self.request("put", self.fixture.worker, data={"user_id": self.fixture.admin.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectFavorite.objects.count(), 2)
        for _ in range(2):
            self.assertEqual(self.request("delete").json(), {"is_favorite": False})
        self.assertIs(self.detail(self.fixture.worker).json()["is_favorite"], True)
        self.assertIs(self.detail(self.fixture.admin).json()["is_favorite"], False)

    def test_unique_user_project_constraint(self):
        self.request("put")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectFavorite.objects.create(user=self.fixture.admin, project=self.project)

    def test_authentication_and_object_visibility_are_checked_for_both_methods(self):
        for method in ("put", "delete"):
            self.assertEqual(self.fixture.request(method, self.path).status_code, 401)
            self.assertEqual(self.request(method, self.fixture.outsider).status_code, 404)
        self.assertEqual(ProjectFavorite.objects.count(), 0)

    def test_membership_area_archiving_and_role_revocation_prevent_mutation(self):
        worker = self.fixture.worker
        self.assertEqual(self.request("put", worker).status_code, 200)
        ProjectMember.objects.filter(project=self.project, worker=worker.worker).update(active=False)
        for method in ("put", "delete"):
            self.assertEqual(self.request(method, worker).status_code, 404)
        ProjectMember.objects.filter(project=self.project, worker=worker.worker).update(active=True)
        WorkerArea.objects.filter(worker=worker.worker).delete()
        type(worker.worker).objects.filter(pk=worker.worker_id).update(area=self.fixture.other_area)
        for method in ("put", "delete"):
            self.assertEqual(self.request(method, worker).status_code, 404)
        Project.objects.filter(pk=self.project.pk).update(archived=True)
        for method in ("put", "delete"):
            self.assertEqual(self.request(method).status_code, 404)
        Project.objects.filter(pk=self.project.pk).update(archived=False)
        worker.userrole_set.all().delete()
        for method in ("put", "delete"):
            self.assertIn(self.request(method, worker).status_code, (401, 403))
        self.assertEqual(ProjectFavorite.objects.count(), 1)

    def test_database_error_preserves_previous_preference(self):
        with patch("apps.projects.services.favorites.ProjectFavorite.objects.get_or_create", side_effect=OperationalError()):
            self.assertEqual(self.request("put").status_code, 503)
        self.assertEqual(ProjectFavorite.objects.count(), 0)
        self.assertIs(self.detail(self.fixture.admin).json()["is_favorite"], False)

    def test_project_list_does_not_query_favorites_per_project(self):
        self.request("put")
        with CaptureQueriesContext(connection) as queries:
            response = self.fixture.request("get", user=self.fixture.admin)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any("proyecto_favorito" in query["sql"] for query in queries))
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.detail(self.fixture.admin).status_code, 200)
        self.assertEqual(sum("proyecto_favorito" in query["sql"] for query in queries), 1)


class ProjectFavoriteMigrationTests(unittest.TestCase):
    def test_0008_creates_and_reverses_only_favorites_table(self):
        if os.environ.get("AUTH_TEST_SQLITE") != "1" or connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
            raise unittest.SkipTest("Requires explicit isolated SQLite memory settings")
        self.assertEqual(connection.introspection.table_names(), [])
        migration = import_module("apps.projects.migrations.0008_project_favorite").Migration("0008_project_favorite", "proyectos")
        state = MigrationLoader(None).project_state([("proyectos", "0007_project_single_area")])
        with connection.schema_editor() as editor:
            migrated = migration.apply(state, editor)
        self.assertEqual(connection.introspection.table_names(), ["proyecto_favorito"])
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "proyecto_favorito")
        self.assertTrue(constraints["uq_proyecto_favorito_usuario"]["unique"])
        self.assertEqual(constraints["uq_proyecto_favorito_usuario"]["columns"], ["usuario_id", "proyecto_id"])
        self.assertEqual(migrated.apps.get_model("proyectos", "ProjectFavorite")._meta.db_table, "proyecto_favorito")
        with connection.schema_editor() as editor:
            migration.unapply(state, editor)
        self.assertEqual(connection.introspection.table_names(), [])
