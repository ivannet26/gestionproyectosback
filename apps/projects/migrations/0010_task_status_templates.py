from importlib import import_module
from pathlib import Path
import os
import re

from django.db import DatabaseError, migrations, models
import django.db.models.deletion


baseline = import_module("apps.projects.migrations.0009_task_assignees")
structure = import_module("apps.projects.migrations.0003_project_sql_policy")
helpers = baseline.baseline.helpers
normalized = baseline.baseline.normalized
BACKUP_KEY = "task_status_templates_0010"
ROUTINES = ("sp_cambiar_estado_actividad", "sp_validar_estructura_actividad")
NEW_ROUTINES = ("fn_regla_estado_actividad", "sp_aplicar_estado_actividad")


def source(name):
    return (Path(__file__).parent / "sql" / f"{name}.0010.sql").read_text(encoding="utf-8")


def review(cursor, installed=False):
    definitions = {}
    for name in ROUTINES:
        definition = helpers.read_definition(cursor, "PROCEDURE", name)
        expected = source(name) if installed else baseline.source() if name == ROUTINES[0] else structure.source(name)
        if normalized(definition["Create Procedure"]) != normalized(expected):
            raise RuntimeError("Task routine differs from reviewed baseline; preserve and review")
        definitions[name] = definition
    return definitions


def preflight(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    if os.environ.get("TASK_STATUS_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_STATUS_MIGRATION_MAINTENANCE")
    with schema_editor.connection.cursor() as cursor:
        review(cursor)
        cursor.execute("SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() "
                       "AND ROUTINE_NAME IN ('fn_regla_estado_actividad','sp_aplicar_estado_actividad')")
        if cursor.fetchone()[0]:
            raise RuntimeError("New task routines already exist; preserve and review")
        cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                       "AND TABLE_NAME IN ('estado_actividad_definicion','proyecto_plantilla_estados')")
        if cursor.fetchone()[0]:
            raise RuntimeError("New state tables already exist; preserve and review")


def backfill(apps, schema_editor):
    statuses = apps.get_model("proyectos", "ProjectTaskStatus").objects.using(schema_editor.connection.alias)
    states = apps.get_model("proyectos", "TaskState").objects.using(schema_editor.connection.alias)
    for code, terminal in states.values_list("code", "terminal"):
        category = "not_started" if code == "PENDIENTE" else "closed" if terminal or code in ("COMPLETADA", "CANCELADA") else "active"
        color = {"not_started": "#737373", "active": "#2563eb", "closed": "#26834a"}[category]
        color = {"PENDIENTE": "#46545a", "EN_CURSO": "#1678bd", "COMPLETADA": "#248054",
                 "CANCELADA": "#a42a28", "BLOQUEADA": "#a42a28", "EN_REVISION": "#6b3899", "OBSERVADA": "#6b3899"}.get(code, color)
        statuses.filter(code=code).update(category=category, color=color)


def install(apps, schema_editor):
    backfill(apps, schema_editor)
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        definitions = review(cursor)
        backup = apps.get_model("autenticacion", "MigrationBackup").objects.using(schema_editor.connection.alias)
        saved, created = backup.get_or_create(key=BACKUP_KEY, defaults={"payload": definitions})
        if not created and any(saved.payload.get(name) != definitions[name] for name in ROUTINES):
            raise RuntimeError("State migration backup differs; preserve and review")
        try:
            cursor.execute(source(NEW_ROUTINES[0]))
            cursor.execute(source(NEW_ROUTINES[1]))
            for name in ROUTINES:
                sql = source(name)
                original = definitions[name]["Create Procedure"]
                definer = re.search(r"DEFINER\s*=\s*`(?:``|[^`])*`@`(?:``|[^`])*`", original, re.IGNORECASE)
                if definer:
                    sql = sql.replace("CREATE PROCEDURE", f"CREATE {definer.group()} PROCEDURE", 1)
                helpers.recreate(cursor, name, sql, definitions[name])
            review(cursor, installed=True)
            installed = {}
            for name in NEW_ROUTINES:
                kind = "FUNCTION" if name.startswith("fn_") else "PROCEDURE"
                installed[name] = helpers.read_definition(cursor, kind, name)
            saved.payload = {**definitions, "installed_new_routines": installed}
            saved.save(update_fields=["payload"])
        except (DatabaseError, RuntimeError):
            for name in ROUTINES:
                helpers.recreate(cursor, name, definitions[name]["Create Procedure"], definitions[name])
            cursor.execute("DROP PROCEDURE IF EXISTS sp_aplicar_estado_actividad")
            cursor.execute("DROP FUNCTION IF EXISTS fn_regla_estado_actividad")
            raise


def restore(apps, schema_editor):
    alias = schema_editor.connection.alias
    if any(apps.get_model("proyectos", name).objects.using(alias).exists()
           for name in ("TaskStateDefinition", "TaskStatusTemplate")):
        raise RuntimeError("Custom states or templates exist; preserve data before rollback")
    if schema_editor.connection.vendor != "mysql":
        return
    if os.environ.get("TASK_STATUS_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes before restoring routines")
    saved = apps.get_model("autenticacion", "MigrationBackup").objects.using(alias).get(key=BACKUP_KEY)
    with schema_editor.connection.cursor() as cursor:
        review(cursor, installed=True)
        for name in NEW_ROUTINES:
            kind = "FUNCTION" if name.startswith("fn_") else "PROCEDURE"
            definition = helpers.read_definition(cursor, kind, name)
            expected = saved.payload["installed_new_routines"][name][f"Create {kind.title()}"]
            if normalized(definition[f"Create {kind.title()}"]) != normalized(expected):
                raise RuntimeError("New routine changed after migration; preserve and review")
        for name in ROUTINES:
            helpers.recreate(cursor, name, saved.payload[name]["Create Procedure"], saved.payload[name])
        cursor.execute("DROP PROCEDURE sp_aplicar_estado_actividad")
        cursor.execute("DROP FUNCTION fn_regla_estado_actividad")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0009_task_assignees")]
    operations = [
        migrations.RunPython(preflight, migrations.RunPython.noop),
        migrations.AddField("projecttaskstatus", "category", models.CharField(max_length=20, default="active", db_column="categoria")),
        migrations.AddField("projecttaskstatus", "color", models.CharField(max_length=7, default="#737373")),
        migrations.CreateModel(
            name="TaskStateDefinition",
            fields=[
                ("code", models.CharField(primary_key=True, max_length=20, db_column="estado_codigo", serialize=False)),
                ("project", models.ForeignKey(to="proyectos.project", on_delete=django.db.models.deletion.DO_NOTHING,
                                             db_constraint=False, db_column="proyecto_id")),
                ("category", models.CharField(max_length=20, db_column="categoria")),
            ],
            options={"db_table": "estado_actividad_definicion"},
        ),
        migrations.CreateModel(
            name="TaskStatusTemplate",
            fields=[
                ("id", models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name="ID")),
                ("project", models.ForeignKey(to="proyectos.project", on_delete=django.db.models.deletion.DO_NOTHING,
                                             db_constraint=False, db_column="proyecto_id")),
                ("name", models.CharField(max_length=70, db_column="nombre")),
                ("states", models.JSONField(db_column="estados")),
                ("revision", models.PositiveIntegerField(default=1)),
            ],
            options={"db_table": "proyecto_plantilla_estados", "ordering": ["name", "id"],
                     "constraints": [models.UniqueConstraint(fields=("project", "name"), name="uq_proyecto_plantilla_nombre")]},
        ),
        migrations.RunPython(install, restore),
    ]
