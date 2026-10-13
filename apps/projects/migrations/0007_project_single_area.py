from importlib import import_module
from pathlib import Path
import os
import re

from django.db import DatabaseError, migrations


PROCEDURE = "sp_cambiar_estado_actividad"
BACKUP_KEY = "project_single_area_0007"
SQL_DIR = Path(__file__).parent / "sql"
helpers = import_module("apps.authentication.migrations.0004_global_admin_sql_policy")
AUDIT_SQL = """
SELECT p.id, p.codigo, p.nombre, p.area_id, COUNT(pa.area_id),
       GROUP_CONCAT(pa.area_id ORDER BY pa.area_id),
       SUM(CASE WHEN pa.area_id=p.area_id THEN 1 ELSE 0 END)
FROM proyecto p LEFT JOIN proyecto_area pa ON pa.proyecto_id=p.id
GROUP BY p.id, p.codigo, p.nombre, p.area_id
HAVING COUNT(pa.area_id)<>1
    OR SUM(CASE WHEN pa.area_id=p.area_id THEN 1 ELSE 0 END)<>1
"""


def source(updated=True):
    version = "0007" if updated else "0006"
    return (SQL_DIR / f"{PROCEDURE}.{version}.sql").read_text(encoding="utf-8")


def normalized(sql):
    sql = re.sub(r"DEFINER\s*=\s*`(?:``|[^`])*`@`(?:``|[^`])*`\s*", "", sql, flags=re.IGNORECASE)
    parts = re.split(r"('(?:''|\\.|[^'])*'|`(?:``|[^`])*`)", sql)
    return "".join(part if index % 2 else re.sub(r"\s+", " ", part).lower()
                   for index, part in enumerate(parts)).strip().rstrip(";")


def review_procedure(cursor, updated=False):
    definition = helpers.read_definition(cursor, "PROCEDURE", PROCEDURE)
    if normalized(definition["Create Procedure"]) != normalized(source(updated)):
        raise RuntimeError("Procedure signature, security or body differs from reviewed baseline; stop and review")
    return definition


def table_exists(cursor):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto_area'"
    )
    return bool(cursor.fetchone()[0])


def review_data(cursor):
    cursor.execute(AUDIT_SQL)
    affected = cursor.fetchall()
    if affected:
        raise RuntimeError(f"Project area inconsistencies; no automatic reconciliation: {affected!r}")
    cursor.execute(
        "SELECT pa.proyecto_id,pa.area_id FROM proyecto_area pa "
        "LEFT JOIN proyecto p ON p.id=pa.proyecto_id LEFT JOIN area a ON a.id=pa.area_id "
        "WHERE p.id IS NULL OR a.id IS NULL"
    )
    orphans = cursor.fetchall()
    if orphans:
        raise RuntimeError(f"Orphan project area associations; preserve and review: {orphans!r}")


def review_schema(cursor):
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto_area' ORDER BY COLUMN_NAME"
    )
    if cursor.fetchall() != (("area_id",), ("proyecto_id",)):
        raise RuntimeError("Unexpected project area columns; preserve table and review")
    cursor.execute(
        "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto' AND COLUMN_NAME='area_id'"
    )
    if cursor.fetchone() != ("NO",):
        raise RuntimeError("Project area must already be NOT NULL; review schema")
    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto' AND COLUMN_NAME='area_id' "
        "AND REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME='area' AND REFERENCED_COLUMN_NAME='id'"
    )
    if not cursor.fetchall():
        raise RuntimeError("Project area foreign key is missing; review schema")
    cursor.execute(
        "SELECT p.id,p.area_id FROM proyecto p LEFT JOIN area a ON a.id=p.area_id WHERE a.id IS NULL"
    )
    if cursor.fetchall():
        raise RuntimeError("Project references a missing area; preserve data and review")


def review_dependencies(cursor):
    checks = (
        ("ROUTINES", "ROUTINE_NAME", "ROUTINE_DEFINITION", "ROUTINE_SCHEMA"),
        ("VIEWS", "TABLE_NAME", "VIEW_DEFINITION", "TABLE_SCHEMA"),
        ("TRIGGERS", "TRIGGER_NAME", "ACTION_STATEMENT", "TRIGGER_SCHEMA"),
        ("EVENTS", "EVENT_NAME", "EVENT_DEFINITION", "EVENT_SCHEMA"),
    )
    for table, name, definition, schema in checks:
        kind = "ROUTINE_TYPE" if table == "ROUTINES" else "NULL"
        cursor.execute(f"SELECT {name},{definition},{kind} FROM information_schema.{table} WHERE {schema}=DATABASE()")
        for object_name, text, routine_type in cursor.fetchall():
            if text is None:
                raise RuntimeError(f"Cannot inspect {table}.{object_name}; review metadata permissions")
            if re.search(r"\bproyecto_area\b", text, re.IGNORECASE) and not (
                table == "ROUTINES" and object_name == PROCEDURE and routine_type == "PROCEDURE"
            ):
                raise RuntimeError(f"Unreviewed dependency {table}.{object_name}; preserve table and review")
    cursor.execute(
        "SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME='proyecto_area'"
    )
    if cursor.fetchall():
        raise RuntimeError("Foreign keys reference proyecto_area; preserve table and review")
    cursor.execute(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
        "WHERE EVENT_OBJECT_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE='proyecto_area'"
    )
    if cursor.fetchall():
        raise RuntimeError("Triggers belong to proyecto_area; preserve table and review")


def install(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        raise RuntimeError("Project area retirement requires reviewed MySQL schema")
    if os.environ.get("PROJECT_AREA_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop application writers and set PROJECT_AREA_MIGRATION_MAINTENANCE=1 before migration")
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = connection.alias
    with connection.cursor() as cursor:
        saved = backup.objects.using(alias).filter(key=BACKUP_KEY).first()
        if not table_exists(cursor):
            if saved is None or saved.payload.get("phase") not in ("procedure_installed", "table_removed"):
                raise RuntimeError("Project area table is missing without a verified migration checkpoint")
            review_procedure(cursor, updated=True)
            review_dependencies(cursor)
            saved.payload["phase"] = "table_removed"
            saved.save(using=alias, update_fields=["payload"])
            return
        review_schema(cursor)
        review_data(cursor)
        review_dependencies(cursor)
        if saved is None:
            definition = review_procedure(cursor)
            table = helpers.read_definition(cursor, "TABLE", "proyecto_area")
            saved = backup.objects.using(alias).create(
                key=BACKUP_KEY, payload={"procedure": definition, "table": table["Create Table"], "phase": "reviewed"}
            )
        else:
            if saved.payload.get("phase") not in ("reviewed", "procedure_installed"):
                raise RuntimeError("Project area table reappeared or checkpoint is invalid; review recovery")
            live = helpers.read_definition(cursor, "PROCEDURE", PROCEDURE)
            if normalized(live["Create Procedure"]) not in (normalized(source()), normalized(source(False))):
                raise RuntimeError("Procedure changed during incomplete migration; review recovery")
            if normalized(saved.payload["procedure"]["Create Procedure"]) != normalized(source(False)):
                raise RuntimeError("Migration backup differs from baseline; review recovery")
        try:
            helpers.recreate(cursor, PROCEDURE, source(), saved.payload["procedure"])
            review_procedure(cursor, updated=True)
        except (DatabaseError, RuntimeError):
            helpers.recreate(cursor, PROCEDURE, saved.payload["procedure"]["Create Procedure"], saved.payload["procedure"])
            raise
        saved.payload["phase"] = "procedure_installed"
        saved.save(using=alias, update_fields=["payload"])
        review_data(cursor)
        review_dependencies(cursor)
        cursor.execute("DROP TABLE proyecto_area")
        saved.payload["phase"] = "table_removed"
        saved.save(using=alias, update_fields=["payload"])


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0006_task_descriptions_and_project_states")]
    operations = [
        migrations.RunPython(install),
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="ProjectArea")],
        ),
    ]
