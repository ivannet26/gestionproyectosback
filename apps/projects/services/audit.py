from contextlib import contextmanager

from django.db import DatabaseError, connection
from rest_framework.exceptions import PermissionDenied


@contextmanager
def audit_actor(user):
    if user.global_role not in ("ADMINISTRADOR", "TRABAJADOR"):
        raise PermissionDenied("Cuenta no autorizada")
    if connection.vendor != "mysql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SET @gm_usuario_id = %s", [user.pk])
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET @gm_usuario_id = NULL")
        except DatabaseError:
            connection.close()
