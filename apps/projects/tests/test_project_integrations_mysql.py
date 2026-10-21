from . import test_project_integrations as cases
from . import test_task_detail_mysql as fixtures


class ProjectIntegrationMySQLTests(cases.ProjectIntegrationTests):
    setUpClass = classmethod(fixtures.TaskDetailMySQLTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.TaskDetailMySQLTests.tearDownClass.__func__)
    setUp = fixtures.TaskDetailMySQLTests.setUp
    tearDown = fixtures.TaskDetailMySQLTests.tearDown

    def test_move_deliverables_are_previewed_and_revalidated_by_real_procedure(self):
        from django.db import connection
        from apps.projects.models import TaskActivity, TaskOrder
        project = self.assigned_project()
        task = self.task(project, state_code="EN_REVISION", responsible_id=self.worker.worker_id)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO test_entregable VALUES(%s,1,'PENDIENTE')", [task.pk])
        self.assertNotIn("COMPLETADA", self.snapshot(project, task)["move_targets"])
        count = TaskActivity.objects.count()
        positions = dict(TaskOrder.objects.values_list("task_id", "position"))
        self.assertEqual(self.move(project, task, "COMPLETADA").status_code, 409)
        self.assertEqual(TaskActivity.objects.count(), count)
        self.assertEqual(dict(TaskOrder.objects.values_list("task_id", "position")), positions)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE test_entregable SET estado_revision='APROBADO' WHERE actividad_id=%s", [task.pk])
        self.assertIn("COMPLETADA", self.snapshot(project, task)["move_targets"])
        self.assertEqual(self.move(project, task, "COMPLETADA").status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.state_code, "COMPLETADA")
