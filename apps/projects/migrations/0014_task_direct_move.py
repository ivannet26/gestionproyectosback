import os
import re
from importlib import import_module

from django.db import DatabaseError, migrations


baseline = import_module("apps.projects.migrations.0010_task_status_templates")
NAME = "sp_aplicar_estado_actividad"
MODE = "sp_aplicar_estado_actividad_modo"
KEY = "task_direct_move_0014"


def source():
    original = baseline.source(NAME)
    marker = " IF EXISTS(SELECT 1 FROM estado_actividad_definicion WHERE proyecto_id=p_proyecto AND estado_codigo IN (v_origen,p_destino)) THEN"
    if original.count(marker) != 1:
        raise RuntimeError("Direct move policy requires review")
    branch = """ IF p_movimiento THEN
  SET v_req_supervision=v_regla_destino IN ('COMPLETADA','CANCELADA') OR v_regla_origen IN ('COMPLETADA','CANCELADA');
  SELECT (v_req_supervision OR COALESCE(MAX(requiere_supervision),0)) INTO v_req_supervision
  FROM transicion_actividad WHERE origen=v_regla_origen AND destino=v_regla_destino;
  SET v_req_motivo=FALSE;
 ELSEIF EXISTS(SELECT 1 FROM estado_actividad_definicion WHERE proyecto_id=p_proyecto AND estado_codigo IN (v_origen,p_destino)) THEN"""
    return original.replace(f"`{NAME}`", f"`{MODE}`", 1).replace(
        "IN p_motivo VARCHAR(500))", "IN p_motivo VARCHAR(500), IN p_movimiento BOOLEAN)", 1
    ).replace(marker, branch, 1)


def wrapper():
    return f"""CREATE PROCEDURE `{NAME}`(IN p_proyecto BIGINT UNSIGNED,
 IN p_actividad BIGINT UNSIGNED,IN p_destino VARCHAR(20),IN p_motivo VARCHAR(500))
 SQL SECURITY INVOKER
BEGIN
 CALL {MODE}(p_proyecto,p_actividad,p_destino,p_motivo,FALSE);
END"""


def maintained(connection):
    if os.environ.get("TASK_MOVE_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_MOVE_MIGRATION_MAINTENANCE")


def with_definer(sql, original):
    match = re.search(r"DEFINER\s*=\s*`(?:``|[^`])*`@`(?:``|[^`])*`", original, re.IGNORECASE)
    return sql.replace("CREATE PROCEDURE", f"CREATE {match.group()} PROCEDURE", 1) if match else sql


def install(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    maintained(connection)
    with connection.cursor() as cursor:
        original = baseline.helpers.read_definition(cursor, "PROCEDURE", NAME)
        if baseline.normalized(original["Create Procedure"]) != baseline.normalized(baseline.source(NAME)):
            raise RuntimeError("Task routine differs from reviewed baseline; preserve and review")
        cursor.execute("SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() AND ROUTINE_NAME=%s", [MODE])
        if cursor.fetchone()[0]:
            raise RuntimeError("Direct move routine already exists; preserve and review")
        backup = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias)
        saved, created = backup.get_or_create(key=KEY, defaults={"payload": original})
        if not created and saved.payload != original:
            raise RuntimeError("Task move backup differs; preserve and review")
        try:
            baseline.helpers.recreate(cursor, MODE, with_definer(source(), original["Create Procedure"]), original)
            baseline.helpers.recreate(cursor, NAME, with_definer(wrapper(), original["Create Procedure"]), original)
        except (DatabaseError, RuntimeError):
            baseline.helpers.recreate(cursor, NAME, original["Create Procedure"], original)
            cursor.execute(f"DROP PROCEDURE IF EXISTS {MODE}")
            raise


def restore(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    maintained(connection)
    with connection.cursor() as cursor:
        for name, expected in ((NAME, wrapper()), (MODE, source())):
            definition = baseline.helpers.read_definition(cursor, "PROCEDURE", name)
            if baseline.normalized(definition["Create Procedure"]) != baseline.normalized(expected):
                raise RuntimeError("Task move routine changed; preserve and review")
        saved = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias).get(key=KEY)
        baseline.helpers.recreate(cursor, NAME, saved.payload["Create Procedure"], saved.payload)
        cursor.execute(f"DROP PROCEDURE {MODE}")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0013_project_teams_specialties_order")]
    operations = [migrations.RunPython(install, restore)]
