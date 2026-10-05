from pathlib import Path
import re

from django.db import migrations


SQL_DIR = Path(__file__).parent / "sql"
PROCEDURES = ("sp_validar_supervisor", "sp_cambiar_estado_actividad")


def body(sql):
    match = re.search(r"\bBEGIN\b", sql, re.IGNORECASE)
    if match is None:
        raise RuntimeError("Routine definition requires review")
    return re.sub(r"\s+", " ", sql[match.start():]).strip().rstrip(";").lower()


def read_definition(cursor, kind, name):
    cursor.execute(f"SHOW CREATE {kind} {name}")
    return dict(zip((column[0] for column in cursor.description), cursor.fetchone()))


def recreate(cursor, name, definition, metadata=None):
    previous = None
    if metadata and "sql_mode" in metadata:
        cursor.execute("SELECT @@SESSION.sql_mode")
        previous = cursor.fetchone()[0]
        cursor.execute("SET SESSION sql_mode = %s", [metadata["sql_mode"]])
    try:
        cursor.execute(f"DROP PROCEDURE IF EXISTS {name}")
        cursor.execute(definition)
    finally:
        if previous is not None:
            cursor.execute("SET SESSION sql_mode = %s", [previous])


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        definitions = {name: read_definition(cursor, "PROCEDURE", name) for name in PROCEDURES}
        availability = read_definition(cursor, "VIEW", "v_disponibilidad_actual")
        cursor.execute("SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'v_trabajador_area_autorizada'")
        if cursor.fetchone()[0] and not backup.objects.using(alias).filter(key="sql_policy_0004").exists():
            raise RuntimeError("Authorized area view already exists; review it before migration")
        for name, definition in definitions.items():
            baseline = (SQL_DIR / f"{name}.before.sql").read_text(encoding="utf-8")
            desired = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
            if body(definition["Create Procedure"]) not in (body(baseline), body(desired)):
                raise RuntimeError("Live SQL routine differs from reviewed baseline; review it before applying")
        saved, _ = backup.objects.using(alias).get_or_create(
            key="sql_policy_0004", defaults={"payload": {"procedures": definitions, "availability": availability}},
        )
        cursor.execute((SQL_DIR / "v_trabajador_area_autorizada.sql").read_text(encoding="utf-8").replace("CREATE SQL SECURITY", "CREATE OR REPLACE SQL SECURITY", 1))
        cursor.execute((SQL_DIR / "v_disponibilidad_actual.sql").read_text(encoding="utf-8").replace("CREATE SQL SECURITY", "CREATE OR REPLACE SQL SECURITY", 1))
        for name in PROCEDURES:
            recreate(cursor, name, (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"), saved.payload["procedures"][name])


def restore(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    saved = backup.objects.using(schema_editor.connection.alias).get(key="sql_policy_0004")
    with schema_editor.connection.cursor() as cursor:
        for name in PROCEDURES:
            live = read_definition(cursor, "PROCEDURE", name)
            expected = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
            if body(live["Create Procedure"]) != body(expected):
                raise RuntimeError("SQL routine changed after migration; review rollback")
        for name, definition in saved.payload["procedures"].items():
            recreate(cursor, name, definition["Create Procedure"], definition)
        original_view = saved.payload["availability"]["Create View"]
        cursor.execute(re.sub(r"^CREATE\b", "CREATE OR REPLACE", original_view, count=1, flags=re.IGNORECASE))
        cursor.execute("DROP VIEW v_trabajador_area_autorizada")
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("autenticacion", "0003_final_roles_and_existing_areas")]
    operations = [migrations.RunPython(install, restore)]
