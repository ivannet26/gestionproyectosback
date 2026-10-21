import os
from pathlib import Path

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


TRIGGER = "gm_au_actividad_historial"


def maintained(connection):
    if connection.vendor == "mysql" and os.environ.get("TASK_DETAIL_MIGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop task writes and enable TASK_DETAIL_MIGRATION_MAINTENANCE")


def add_duration(apps, schema_editor):
    connection = schema_editor.connection
    maintained(connection)
    with connection.cursor() as cursor:
        if {"actividad_historial", "actividad_relacion"} & set(connection.introspection.table_names(cursor)):
            raise RuntimeError("Task detail tables already exist; preserve and review")
        if "duracion_estimada_minutos" in {column.name for column in connection.introspection.get_table_description(cursor, "actividad")}:
            raise RuntimeError("Estimated duration column already exists; preserve and review")
        if connection.vendor == "mysql":
            cursor.execute("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME=%s", [TRIGGER])
            if cursor.fetchone()[0]:
                raise RuntimeError("Activity trigger already exists; preserve and review")
        column_type = "INTEGER UNSIGNED" if connection.vendor == "mysql" else "INTEGER"
        cursor.execute(f"ALTER TABLE actividad ADD COLUMN duracion_estimada_minutos {column_type} NULL CHECK(duracion_estimada_minutos IS NULL OR (duracion_estimada_minutos>0 AND duracion_estimada_minutos<=2147483647))")


def remove_duration(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE actividad DROP COLUMN duracion_estimada_minutos")


def install(apps, schema_editor):
    connection = schema_editor.connection
    maintained(connection)
    if connection.vendor == "mysql":
        sql = (Path(__file__).parent / "sql/gm_au_actividad_historial.0012.sql").read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            cursor.execute(sql)


def uninstall(apps, schema_editor):
    connection = schema_editor.connection
    maintained(connection)
    with connection.cursor() as cursor:
        for sql in ("SELECT COUNT(*) FROM actividad_historial", "SELECT COUNT(*) FROM actividad_relacion",
                    "SELECT COUNT(*) FROM actividad WHERE duracion_estimada_minutos IS NOT NULL"):
            cursor.execute(sql)
            if cursor.fetchone()[0]:
                raise RuntimeError("Task detail data exists; rollback requires an explicit preservation plan")
        if connection.vendor == "mysql":
            cursor.execute("DROP TRIGGER gm_au_actividad_historial")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0011_task_optional_properties")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_duration, remove_duration)],
            state_operations=[migrations.AddField("task", "estimated_minutes", models.PositiveIntegerField(null=True, blank=True, db_column="duracion_estimada_minutos"))],
        ),
        migrations.CreateModel(name="TaskRelation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=70)), ("name_key", models.CharField(max_length=210)),
            ("project", models.ForeignKey(to="proyectos.project", on_delete=django.db.models.deletion.DO_NOTHING, db_constraint=False, db_column="proyecto_id")),
            ("left_task", models.ForeignKey(to="proyectos.task", on_delete=django.db.models.deletion.DO_NOTHING, db_constraint=False, related_name="relations_left")),
            ("right_task", models.ForeignKey(to="proyectos.task", on_delete=django.db.models.deletion.DO_NOTHING, db_constraint=False, related_name="relations_right")),
        ], options={"db_table": "actividad_relacion", "constraints": [
            models.UniqueConstraint(fields=("project", "left_task", "right_task", "name_key"), name="uq_actividad_relacion"),
            models.CheckConstraint(condition=models.Q(left_task_id__lt=models.F("right_task_id")), name="ck_relacion_distinta"),
        ]}),
        migrations.CreateModel(name="TaskActivity", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("operation_id", models.CharField(max_length=36, db_column="operacion_id")),
            ("actor_id", models.PositiveBigIntegerField(db_column="autor_id")),
            ("actor_name", models.CharField(max_length=225, db_column="autor_nombre")),
            ("action", models.CharField(max_length=32, db_column="accion")),
            ("field", models.CharField(max_length=32, default="", blank=True, db_column="campo")),
            ("old_value", models.JSONField(null=True, db_column="valor_anterior")),
            ("new_value", models.JSONField(null=True, db_column="valor_nuevo")),
            ("related_task_id", models.PositiveBigIntegerField(null=True, db_column="actividad_relacionada_id")),
            ("created_at", models.DateTimeField(default=django.utils.timezone.now, db_column="creado_en")),
            ("project", models.ForeignKey(to="proyectos.project", on_delete=django.db.models.deletion.DO_NOTHING, db_constraint=False, db_column="proyecto_id")),
            ("task", models.ForeignKey(to="proyectos.task", on_delete=django.db.models.deletion.DO_NOTHING, db_constraint=False, db_column="actividad_id")),
        ], options={"db_table": "actividad_historial", "indexes": [models.Index(fields=["task", "operation_id", "id"], name="ix_historial_operacion")]}),
        migrations.RunPython(install, uninstall),
    ]
