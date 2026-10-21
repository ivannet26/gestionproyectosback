from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from django.db import DatabaseError, connection
from rest_framework.exceptions import PermissionDenied

from ..models import TaskActivity


operation = ContextVar("task_audit_operation", default=None)


def record_activity(task, action, *, field="", old=None, new=None, related_task_id=None):
    context = operation.get()
    if context is None:
        raise RuntimeError("Task activity requires an authenticated operation")
    user, operation_id = context
    TaskActivity.objects.create(
        project_id=task.project_id, task_id=task.pk, operation_id=operation_id,
        actor_id=user.pk, actor_name=f"{user.worker.first_names} {user.worker.last_names}".strip(),
        action=action, field=field, old_value=old, new_value=new, related_task_id=related_task_id,
    )


@contextmanager
def audit_actor(user):
    if user.global_role not in ("ADMINISTRADOR", "TRABAJADOR"):
        raise PermissionDenied("Cuenta no autorizada")
    previous = operation.get()
    current = previous if previous and previous[0].pk == user.pk else (user, str(uuid4()))
    context_token = operation.set(current)
    try:
        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("SET @gm_usuario_id = %s, @gm_operacion_id = %s", [user.pk, current[1]])
        yield
    finally:
        operation.reset(context_token)
        try:
            if connection.vendor == "mysql":
                with connection.cursor() as cursor:
                    if previous:
                        cursor.execute("SET @gm_usuario_id = %s, @gm_operacion_id = %s", [previous[0].pk, previous[1]])
                    else:
                        cursor.execute("SET @gm_usuario_id = NULL, @gm_operacion_id = NULL, @gm_estados_anteriores = NULL")
        except DatabaseError:
            connection.close()
