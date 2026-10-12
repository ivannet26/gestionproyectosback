from importlib import import_module
from pathlib import Path
import re

from django.db import migrations, models


SQL_DIR = Path(__file__).parent / "sql"
PROCEDURE = "sp_cambiar_estado_actividad"
BACKUP_KEY = "project_task_states_0006"
helpers = import_module("apps.authentication.migrations.0004_global_admin_sql_policy")


def source(updated=True):
    name = f"{PROCEDURE}{'.0006' if updated else ''}.sql"
    return (SQL_DIR / name).read_text(encoding="utf-8")


def review(cursor, updated=False):
    definition = helpers.read_definition(cursor, "PROCEDURE", PROCEDURE)
    if helpers.body(definition["Create Procedure"]) != helpers.body(source(updated)):
        raise RuntimeError("Task state procedure differs from reviewed baseline; review before continuing")
    return definition


def compatible_description_exists(cursor):
    cursor.execute(
        "SELECT DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, GENERATION_EXPRESSION "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        ["actividad", "descripcion"],
    )
    definition = cursor.fetchone()
    if definition is None:
        return False
    if definition != ("text", "text", "YES", None, "", ""):
        raise RuntimeError("Task description must be a normal TEXT NULL column with no non-NULL default; review schema")
    return True


def preflight(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        review(cursor)
        compatible_description_exists(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='proyecto_estado_actividad'"
        )
        if cursor.fetchone()[0]:
            raise RuntimeError("Project task state table already exists; review schema before applying")


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        definition = review(cursor)
        description_exists = compatible_description_exists(cursor)
        cursor.execute(
            "SELECT CHARACTER_SET_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='estado_actividad' AND COLUMN_NAME='codigo'"
        )
        metadata = cursor.fetchone()
        if not metadata or not all(value and re.fullmatch(r"[a-zA-Z0-9_]+", value) for value in metadata):
            raise RuntimeError("State code collation requires review")
        saved = backup.objects.using(alias).create(
            key=BACKUP_KEY, payload={**definition, "description_created": False}
        )
        if not description_exists:
            cursor.execute("ALTER TABLE actividad ADD COLUMN descripcion TEXT NULL")
            saved.payload["description_created"] = True
            saved.save(using=alias, update_fields=["payload"])
        cursor.execute(
            "ALTER TABLE proyecto_estado_actividad MODIFY proyecto_id BIGINT UNSIGNED NOT NULL, "
            f"MODIFY estado_codigo VARCHAR(20) CHARACTER SET {metadata[0]} COLLATE {metadata[1]} NOT NULL, "
            "ADD CONSTRAINT fk_proyecto_estado_proyecto FOREIGN KEY (proyecto_id) REFERENCES proyecto(id), "
            "ADD CONSTRAINT fk_proyecto_estado_codigo FOREIGN KEY (estado_codigo) REFERENCES estado_actividad(codigo)"
        )
        helpers.recreate(cursor, PROCEDURE, source(), saved.payload)


def restore(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    saved = backup.objects.using(schema_editor.connection.alias).get(key=BACKUP_KEY)
    description_created = saved.payload.get("description_created")
    if not isinstance(description_created, bool):
        raise RuntimeError("Task description ownership is missing or invalid; review rollback before changing schema")
    with schema_editor.connection.cursor() as cursor:
        if description_created:
            if not compatible_description_exists(cursor):
                raise RuntimeError("Migration-created task description is missing; review rollback")
            cursor.execute("SELECT EXISTS(SELECT 1 FROM actividad WHERE descripcion IS NOT NULL AND descripcion<>'')")
            if cursor.fetchone()[0]:
                raise RuntimeError("Task descriptions are in use; preserve them before rollback")
        cursor.execute("SELECT EXISTS(SELECT 1 FROM proyecto_estado_actividad)")
        if cursor.fetchone()[0]:
            raise RuntimeError("Project states are in use; preserve them before rollback")
        review(cursor, updated=True)
        helpers.recreate(cursor, PROCEDURE, saved.payload["Create Procedure"], saved.payload)
        if description_created:
            cursor.execute("ALTER TABLE actividad DROP COLUMN descripcion")
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0005_project_worker_create")]
    operations = [
        migrations.RunPython(preflight, migrations.RunPython.noop),
        migrations.CreateModel(
            name="ProjectTaskStatus",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "project_id", "code", blank=True, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("code", models.CharField(max_length=20, db_column="estado_codigo")),
                ("name", models.CharField(max_length=70, db_column="nombre")),
                ("position", models.PositiveSmallIntegerField(db_column="orden")),
                (
                    "project",
                    models.ForeignKey(
                        to="proyectos.project", on_delete=models.DO_NOTHING,
                        db_column="proyecto_id", db_constraint=False,
                    ),
                ),
            ],
            options={
                "db_table": "proyecto_estado_actividad",
                "ordering": ["position", "code"],
                "constraints": [
                    models.UniqueConstraint(fields=["project", "name"], name="uq_proyecto_estado_nombre"),
                    models.UniqueConstraint(fields=["project", "position"], name="uq_proyecto_estado_orden"),
                ],
            },
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install, restore)],
            state_operations=[
                migrations.AddField(
                    model_name="task", name="description",
                    field=models.TextField(null=True, blank=True, db_column="descripcion"),
                ),
            ],
        ),
    ]
