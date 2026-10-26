from importlib import import_module
from pathlib import Path
import os

from django.db import DatabaseError, migrations


previous = import_module("apps.projects.migrations.0015_task_state_without_assignee")
direct = previous.previous
baseline = direct.baseline
helpers = baseline.helpers
KEY = "task_state_policy_consistency_0016"
NAMES = (direct.NAME, direct.MODE)
REASON = """ IF v_req_motivo=1 AND (p_motivo IS NULL OR CHAR_LENGTH(TRIM(p_motivo))=0) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Debe indicar el motivo del cambio.';
 END IF;
"""
ASSIGNEE = """  IF v_responsable IS NULL OR NOT EXISTS(SELECT 1 FROM proyecto_miembro pm JOIN trabajador t ON t.id=pm.trabajador_id
   WHERE pm.proyecto_id=p_proyecto AND pm.trabajador_id=v_responsable AND pm.activo=1 AND t.activo=1) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La actividad debe tener un responsable activo del proyecto.';
  END IF;
"""


def source(name):
    if name == direct.NAME:
        return (Path(__file__).parent / "sql" / "sp_aplicar_estado_actividad.0016.sql").read_text(encoding="utf-8")
    return f"""CREATE PROCEDURE `{direct.MODE}`(IN p_proyecto BIGINT UNSIGNED,
 IN p_actividad BIGINT UNSIGNED,IN p_destino VARCHAR(20),IN p_motivo VARCHAR(500),IN p_movimiento BOOLEAN)
SQL SECURITY INVOKER
BEGIN
 CALL {direct.NAME}(p_proyecto,p_actividad,p_destino,p_motivo);
END"""


def historical(name, reason=False, assignee=False):
    if name == direct.NAME:
        return direct.wrapper()
    sql = direct.source()
    if reason:
        marker = " IF v_regla_destino NOT IN ('COMPLETADA','CANCELADA') THEN\n"
        if sql.count(marker) != 1:
            raise RuntimeError("Historical reason policy requires review")
        sql = sql.replace(marker, REASON + marker, 1)
    if assignee:
        marker = " IF v_regla_destino IN ('EN_CURSO','EN_REVISION','COMPLETADA') THEN\n"
        if sql.count(marker) != 1:
            raise RuntimeError("Historical assignee policy requires review")
        sql = sql.replace(marker, marker + ASSIGNEE, 1)
    return sql


def reviewed(definition, name, installed=False):
    candidates = [source(name)] if installed else [historical(name), historical(name, True), historical(name, True, True), source(name)]
    if baseline.normalized(definition["Create Procedure"]) not in {baseline.normalized(sql) for sql in candidates}:
        raise RuntimeError("Task state policy differs from reviewed definitions; preserve and review")


def maintained(connection):
    if connection.vendor == "mysql" and os.environ.get("TASK_STATE_POLICY_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_STATE_POLICY_MAINTENANCE")


def install(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    maintained(connection)
    with connection.cursor() as cursor:
        originals = {name: helpers.read_definition(cursor, "PROCEDURE", name) for name in NAMES}
        for name, definition in originals.items():
            reviewed(definition, name)
        backups = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias)
        saved, created = backups.get_or_create(key=KEY, defaults={"payload": {"procedures": originals}})
        if set(saved.payload.get("procedures", {})) != set(NAMES):
            raise RuntimeError("Task state policy backup requires review")
        for name, definition in saved.payload["procedures"].items():
            reviewed(definition, name)
            if not created and baseline.normalized(originals[name]["Create Procedure"]) not in (
                baseline.normalized(definition["Create Procedure"]), baseline.normalized(source(name)),
            ):
                raise RuntimeError("Task state policy backup differs; preserve and review")
        try:
            for name in NAMES:
                definition = originals[name]
                helpers.recreate(cursor, name, direct.with_definer(source(name), definition["Create Procedure"]), definition)
                reviewed(helpers.read_definition(cursor, "PROCEDURE", name), name, installed=True)
        except (DatabaseError, RuntimeError):
            for name, definition in reversed(list(originals.items())):
                helpers.recreate(cursor, name, definition["Create Procedure"], definition)
            raise


def restore(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    maintained(connection)
    with connection.cursor() as cursor:
        current = {name: helpers.read_definition(cursor, "PROCEDURE", name) for name in NAMES}
        for name, definition in current.items():
            reviewed(definition, name, installed=True)
        saved = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias).get(key=KEY)
        originals = saved.payload.get("procedures", {})
        if set(originals) != set(NAMES):
            raise RuntimeError("Task state policy backup requires review")
        for name, definition in originals.items():
            reviewed(definition, name)
        try:
            for name, definition in reversed(list(originals.items())):
                helpers.recreate(cursor, name, definition["Create Procedure"], definition)
        except (DatabaseError, RuntimeError):
            for name, definition in reversed(list(current.items())):
                helpers.recreate(cursor, name, definition["Create Procedure"], definition)
            raise
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0015_task_state_without_assignee")]
    operations = [migrations.RunPython(install, restore)]
