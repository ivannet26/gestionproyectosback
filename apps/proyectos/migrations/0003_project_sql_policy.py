from importlib import import_module
from pathlib import Path
import re

from django.db import migrations


SQL_DIR = Path(__file__).parent / "sql"
PROCEDURES = ("sp_validar_estructura_actividad", "sp_agregar_dependencia", "sp_cambiar_estado_actividad")
TRIGGER = "bu_actividad_estructura"
VIEW = "v_actividad_hoja"
BACKUP_KEY = "project_sql_0003"
helpers = import_module("apps.autenticacion.migrations.0004_global_admin_sql_policy")


def source(name, before=False):
    return (SQL_DIR / f"{name}{'.before' if before else ''}.sql").read_text(encoding="utf-8")


def view_body(sql):
    match = re.search(r"\bAS\s+SELECT\b", sql, re.IGNORECASE)
    if match is None:
        raise RuntimeError("View requires review")
    return re.sub(r'[\s`"();]+', "", sql[match.end() - 6:]).lower()


def review(cursor):
    definitions = {name: helpers.read_definition(cursor, "PROCEDURE", name) for name in PROCEDURES}
    trigger = helpers.read_definition(cursor, "TRIGGER", TRIGGER)
    view = helpers.read_definition(cursor, "VIEW", VIEW)
    for name, definition in definitions.items():
        if helpers.body(definition["Create Procedure"]) not in (helpers.body(source(name, True)), helpers.body(source(name))):
            raise RuntimeError("SQL procedure differs from reviewed baseline; review before applying")
    if helpers.body(trigger["SQL Original Statement"]) not in (helpers.body(source(TRIGGER, True)), helpers.body(source(TRIGGER))):
        raise RuntimeError("SQL trigger differs from reviewed baseline; review before applying")
    return {"procedures": definitions, "trigger": {key: str(value) if not isinstance(value, (str, int, type(None))) else value for key, value in trigger.items()}, "view": view}


def replace_trigger(cursor, definition, metadata):
    cursor.execute("SELECT @@SESSION.sql_mode")
    previous = cursor.fetchone()[0]
    try:
        cursor.execute("SET SESSION sql_mode=%s", [metadata["sql_mode"]])
        cursor.execute(f"DROP TRIGGER IF EXISTS {TRIGGER}")
        cursor.execute(definition)
    finally:
        cursor.execute("SET SESSION sql_mode=%s", [previous])


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        definitions = review(cursor)
        saved = backup.objects.using(alias).filter(key=BACKUP_KEY).first()
        expected_view = saved.payload.get("installed_view") if saved else None
        if view_body(definitions["view"]["Create View"]) not in (view_body(source(VIEW, True)), view_body(expected_view) if expected_view else view_body(source(VIEW))):
            raise RuntimeError("SQL view differs from reviewed baseline; review before applying")
        if saved is None:
            saved = backup.objects.using(alias).create(key=BACKUP_KEY, payload=definitions)
        for name in PROCEDURES:
            helpers.recreate(cursor, name, source(name), saved.payload["procedures"][name])
        replace_trigger(cursor, source(TRIGGER), saved.payload["trigger"])
        cursor.execute(source(VIEW))
        saved.payload["installed_view"] = helpers.read_definition(cursor, "VIEW", VIEW)["Create View"]
        saved.save(update_fields=["payload"])


def restore(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    saved = backup.objects.using(schema_editor.connection.alias).get(key=BACKUP_KEY)
    schema = import_module("apps.proyectos.migrations.0002_project_schema")
    with schema_editor.connection.cursor() as cursor:
        schema.ensure_unused(cursor)
        definitions = review(cursor)
        for name, definition in definitions["procedures"].items():
            if helpers.body(definition["Create Procedure"]) != helpers.body(source(name)):
                raise RuntimeError("SQL procedure changed after migration; review rollback")
        if helpers.body(definitions["trigger"]["SQL Original Statement"]) != helpers.body(source(TRIGGER)):
            raise RuntimeError("SQL trigger changed after migration; review rollback")
        if view_body(definitions["view"]["Create View"]) != view_body(saved.payload["installed_view"]):
            raise RuntimeError("SQL view changed after migration; review rollback")
        for name, definition in saved.payload["procedures"].items():
            helpers.recreate(cursor, name, definition["Create Procedure"], definition)
        replace_trigger(cursor, saved.payload["trigger"]["SQL Original Statement"], saved.payload["trigger"])
        cursor.execute(re.sub(r"^CREATE\b", "CREATE OR REPLACE", saved.payload["view"]["Create View"], count=1, flags=re.IGNORECASE))
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0002_project_schema")]
    operations = [migrations.RunPython(install, restore)]
