from importlib import import_module
from pathlib import Path
import os
import re

from django.db import DatabaseError, migrations, models


baseline = import_module("apps.projects.migrations.0010_task_status_templates")
helpers = baseline.helpers
ROUTINE = "sp_validar_estructura_actividad"
BACKUP_KEY = "task_optional_properties_0011"


def source(name=ROUTINE):
    return (Path(__file__).parent / "sql" / f"{name}.0011.sql").read_text(encoding="utf-8")


def trigger_review(cursor, installed=False):
    definition = helpers.read_definition(cursor, "TRIGGER", baseline.structure.TRIGGER)
    expected = source(baseline.structure.TRIGGER) if installed else baseline.structure.source(baseline.structure.TRIGGER)
    if helpers.body(definition["SQL Original Statement"]) != helpers.body(expected):
        raise RuntimeError("Task structure trigger differs; preserve and review")
    return {key: value if isinstance(value, (str, int, type(None))) else str(value) for key, value in definition.items()}


def with_definer(sql, original, kind):
    definer = re.search(r"DEFINER\s*=\s*`(?:``|[^`])*`@`(?:``|[^`])*`", original, re.IGNORECASE)
    return sql.replace(f"CREATE {kind}", f"CREATE {definer.group()} {kind}", 1) if definer else sql


def review(cursor, expected):
    definition = helpers.read_definition(cursor, "PROCEDURE", ROUTINE)
    if baseline.normalized(definition["Create Procedure"]) != baseline.normalized(expected):
        raise RuntimeError("Task structure routine differs; preserve and review before migration")
    return definition


def columns(cursor):
    cursor.execute("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,COLUMN_COMMENT "
                   "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='actividad' "
                   "AND COLUMN_NAME IN ('prioridad','fecha_fin')")
    result = {}
    for name, kind, nullable, default, extra, comment in cursor.fetchall():
        if extra or comment or (name == "fecha_fin" and kind != "date") or (
            name == "prioridad" and not re.fullmatch(r"(?:tinyint|smallint)(?:\(\d+\))? unsigned", kind)
        ) or (default is not None and not re.fullmatch(r"[1-4]", str(default))):
            raise RuntimeError("Task column differs from supported legacy types; preserve and review")
        result[name] = {"type": kind, "nullable": nullable, "default": default}
    if set(result) != {"prioridad", "fecha_fin"}:
        raise RuntimeError("Required task columns are missing")
    return result


def alter(cursor, definitions, nullable):
    parts = []
    for name in ("prioridad", "fecha_fin"):
        item = definitions[name]
        default = f" DEFAULT {item['default']}" if item["default"] is not None else " DEFAULT NULL" if nullable else ""
        parts.append(f"MODIFY `{name}` {item['type']} {'NULL' if nullable else 'NOT NULL'}{default}")
    cursor.execute("ALTER TABLE actividad " + ", ".join(parts))


def maintained(schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return False
    if os.environ.get("TASK_OPTIONAL_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_OPTIONAL_MIGRATION_MAINTENANCE")
    return True


def install(apps, schema_editor):
    if not maintained(schema_editor):
        return
    backups = apps.get_model("autenticacion", "MigrationBackup").objects.using(schema_editor.connection.alias)
    with schema_editor.connection.cursor() as cursor:
        saved = backups.filter(key=BACKUP_KEY).first()
        definition = review(cursor, baseline.source(ROUTINE))
        trigger = trigger_review(cursor)
        metadata = columns(cursor)
        if saved is None:
            if any(item["nullable"] != "NO" for item in metadata.values()):
                raise RuntimeError("Task nullability differs from baseline; preserve and review")
            saved = backups.create(key=BACKUP_KEY, payload={"routine": definition, "columns": metadata, "trigger": trigger})
        elif saved.payload["routine"] != definition or saved.payload["trigger"] != trigger or any(
            metadata[name]["type"] != item["type"] or metadata[name]["default"] != item["default"]
            for name, item in saved.payload["columns"].items()
        ):
            raise RuntimeError("Saved task schema differs; preserve and review")
        alter(cursor, saved.payload["columns"], True)
        original = saved.payload["routine"]
        sql = with_definer(source(), original["Create Procedure"], "PROCEDURE")
        try:
            helpers.recreate(cursor, ROUTINE, sql, original)
            baseline.structure.replace_trigger(cursor, with_definer(source(baseline.structure.TRIGGER), trigger["SQL Original Statement"], "TRIGGER"), trigger)
            review(cursor, source())
            trigger_review(cursor, installed=True)
        except (DatabaseError, RuntimeError):
            helpers.recreate(cursor, ROUTINE, original["Create Procedure"], original)
            baseline.structure.replace_trigger(cursor, trigger["SQL Original Statement"], trigger)
            raise


def restore(apps, schema_editor):
    if not maintained(schema_editor):
        return
    backups = apps.get_model("autenticacion", "MigrationBackup").objects.using(schema_editor.connection.alias)
    saved = backups.get(key=BACKUP_KEY)
    with schema_editor.connection.cursor() as cursor:
        review(cursor, source())
        trigger_review(cursor, installed=True)
        metadata = columns(cursor)
        if any(metadata[name]["type"] != item["type"] or metadata[name]["default"] != item["default"]
               for name, item in saved.payload["columns"].items()):
            raise RuntimeError("Task schema changed after migration; preserve and review")
        cursor.execute("SELECT EXISTS(SELECT 1 FROM actividad WHERE fecha_fin IS NULL OR prioridad IS NULL)")
        if cursor.fetchone()[0]:
            raise RuntimeError("Undated or unprioritized tasks exist; rollback requires an explicit preservation plan")
        alter(cursor, saved.payload["columns"], False)
        definition = saved.payload["routine"]
        helpers.recreate(cursor, ROUTINE, definition["Create Procedure"], definition)
        baseline.structure.replace_trigger(cursor, saved.payload["trigger"]["SQL Original Statement"], saved.payload["trigger"])
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0010_task_status_templates")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install, restore)],
            state_operations=[
                migrations.AlterField("task", "priority", models.PositiveSmallIntegerField(default=3, null=True, db_column="prioridad")),
                migrations.AlterField("task", "due_date", models.DateField(null=True, db_column="fecha_fin")),
            ],
        ),
    ]
