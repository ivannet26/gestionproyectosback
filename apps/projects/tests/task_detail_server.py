import json
import os
from pathlib import Path
import secrets
from wsgiref.simple_server import WSGIServer, make_server

import django


class ExclusiveServer(WSGIServer):
    allow_reuse_address = False


def serve():
    if os.environ.get("GM_TASK_DETAIL_BROWSER") != "1":
        raise RuntimeError("Only the isolated task detail browser wrapper may start this fixture")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test_mysql_templates")
    django.setup()

    from django.core.wsgi import get_wsgi_application
    from django.db import connection
    from apps.authentication.models import AuthThrottle, RecoveryRequest
    from apps.organization.models import Specialty
    from apps.workers.models import WorkerSpecialty
    from apps.projects.models import ProjectMember
    from .test_task_detail_mysql import TaskDetailMySQLTests

    TaskDetailMySQLTests.setUpClass()
    fixture = TaskDetailMySQLTests()
    fixture.setUp()
    with connection.schema_editor() as editor:
        for model in (Specialty, WorkerSpecialty, AuthThrottle, RecoveryRequest):
            editor.create_model(model)

    fixture.area.name = "Ingeniería · pruebas aisladas"
    fixture.area.save(update_fields=["name"])
    second = fixture.account("second", "TRABAJADOR", fixture.area)
    for user, name in ((fixture.admin, "Administrador de pruebas"), (fixture.worker, "Ángela QA"), (second, "José QA")):
        user.worker.first_names = name
        user.worker.save(update_fields=["first_names"])
    project = fixture.assigned_project(name="Detalle de tareas · QA", worker_edit=True, worker_contribute=True)
    ProjectMember.objects.create(project=project, worker=second.worker, active=True)
    parent = fixture.task(project, name="Revisión de planos", due_date=None, responsible_ids=[fixture.worker.worker_id, second.worker_id])
    updated = fixture.request("patch", f"{project.pk}/tasks/{parent.pk}/", {"estimated_minutes": 60, "priority": 4}, fixture.admin)
    if updated.status_code != 200:
        raise RuntimeError("No se pudo preparar una operación agrupada real")
    child = fixture.task(project, parent_id=parent.pk, name="Verificar estructura", responsible_id=fixture.worker.worker_id, due_date=None)
    fixture.task(project, parent_id=parent.pk, name="Cálculo aprobado", state_code="COMPLETADA", responsible_id=fixture.worker.worker_id, due_date=None)
    related = fixture.task(project, name="Informe técnico", due_date=None)
    reason_task = fixture.task(project, name="Transición con motivo", due_date=None, responsible_id=fixture.worker.worker_id)
    readonly = fixture.assigned_project(name="Proyecto de solo lectura")
    readonly_task = fixture.task(readonly, name="Consulta sin modificación", responsible_id=fixture.worker.worker_id)
    scrum = fixture.assigned_project(name="Scrum · categoría funcional", worker_edit=True, worker_contribute=True)
    states = fixture.apply(scrum, fixture.preset(scrum, "scrum")).json()["states"]
    scrum_parent = fixture.task(scrum, name="Sprint sintético", state_code=states[0]["code"], due_date=None)
    scrum_child = fixture.task(scrum, parent_id=scrum_parent.pk, name="COMPLETADO aún activo", state_code=states[3]["code"], responsible_id=fixture.worker.worker_id, due_date=None)
    credentials = {}
    for user, role in ((fixture.admin, "admin"), (fixture.worker, "worker"), (fixture.outsider, "outsider")):
        password = secrets.token_urlsafe(24)
        user.set_password(password)
        user.save(update_fields=["password"])
        credentials[role] = {"email": user.worker.email, "password": password}
    credentials["context"] = {"project": project.pk, "task": parent.pk, "child": child.pk, "related": related.pk,
                              "reason_task": reason_task.pk,
                              "readonly": readonly.pk, "readonly_task": readonly_task.pk, "scrum": scrum.pk,
                              "scrum_task": scrum_parent.pk, "scrum_child": scrum_child.pk}
    Path(os.environ["GM_QA_SECRETS_PATH"]).write_text(json.dumps(credentials), encoding="utf-8")

    print("MySQL temporal y Django reales listos; datos exclusivamente sintéticos.", flush=True)
    try:
        with make_server("127.0.0.1", 8819, get_wsgi_application(), server_class=ExclusiveServer) as server:
            server.serve_forever()
    finally:
        connection.close()


if __name__ == "__main__":
    serve()
