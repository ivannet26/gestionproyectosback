from importlib import import_module
from pathlib import Path
import os

from django.db import DatabaseError, migrations, models
import django.db.models.deletion


baseline = import_module("apps.projects.migrations.0007_project_single_area")
PROCEDURE = baseline.PROCEDURE
BACKUP_KEY = "task_assignees_0009"


def source():
    return (Path(__file__).parent / "sql" / f"{PROCEDURE}.0009.sql").read_text(encoding="utf-8")


def reviewed_definition(cursor, updated=False):
    definition = baseline.helpers.read_definition(cursor, "PROCEDURE", PROCEDURE)
    expected = source() if updated else baseline.source()
    if baseline.normalized(definition["Create Procedure"]) != baseline.normalized(expected):
        raise RuntimeError("Task procedure differs from reviewed definition; stop and review")
    return definition


def preflight(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    if os.environ.get("TASK_ASSIGNEE_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_ASSIGNEE_MIGRATION_MAINTENANCE before migration")
    with schema_editor.connection.cursor() as cursor:
        reviewed_definition(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='actividad_responsable_adicional'"
        )
        if cursor.fetchone()[0]:
            raise RuntimeError("Additional assignees table already exists; preserve and review")


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        definition = reviewed_definition(cursor)
        saved, _ = backup.objects.using(alias).get_or_create(key=BACKUP_KEY, defaults={"payload": definition})
        if baseline.normalized(saved.payload["Create Procedure"]) != baseline.normalized(baseline.source()):
            raise RuntimeError("Assignee migration backup differs from reviewed baseline")
        try:
            baseline.helpers.recreate(cursor, PROCEDURE, source(), definition)
            reviewed_definition(cursor, updated=True)
        except (DatabaseError, RuntimeError):
            baseline.helpers.recreate(cursor, PROCEDURE, definition["Create Procedure"], definition)
            raise


def restore(apps, schema_editor):
    alias = schema_editor.connection.alias
    if apps.get_model("proyectos", "TaskAssignee").objects.using(alias).exists():
        raise RuntimeError("Additional assignees exist; preserve and resolve them before rollback")
    if schema_editor.connection.vendor != "mysql":
        return
    if os.environ.get("TASK_ASSIGNEE_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes before restoring the procedure")
    backup = apps.get_model("autenticacion", "MigrationBackup").objects.using(alias).get(key=BACKUP_KEY)
    with schema_editor.connection.cursor() as cursor:
        reviewed_definition(cursor, updated=True)
        baseline.helpers.recreate(cursor, PROCEDURE, backup.payload["Create Procedure"], backup.payload)
        reviewed_definition(cursor)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0008_project_favorite")]
    operations = [
        migrations.RunPython(preflight, migrations.RunPython.noop),
        migrations.CreateModel(
            name="TaskAssignee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task", models.ForeignKey(
                    to="proyectos.task", on_delete=django.db.models.deletion.CASCADE,
                    db_constraint=False, db_column="actividad_id",
                )),
                ("worker", models.ForeignKey(
                    to="workers.worker", on_delete=django.db.models.deletion.DO_NOTHING,
                    db_constraint=False, db_column="trabajador_id",
                )),
            ],
            options={
                "db_table": "actividad_responsable_adicional",
                "constraints": [models.UniqueConstraint(fields=("task", "worker"), name="uq_actividad_responsable_adicional")],
            },
        ),
        migrations.RunPython(install, restore),
    ]
