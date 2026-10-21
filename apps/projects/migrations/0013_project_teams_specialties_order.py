from decimal import Decimal
import os

from django.db import migrations, models
import django.db.models.deletion


def prepare(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "mysql" and os.environ.get("PROJECT_INTEGRATION_MAINTENANCE") != "1":
        raise RuntimeError("Stop project/task writes and enable PROJECT_INTEGRATION_MAINTENANCE")
    with connection.cursor() as cursor:
        if {"proyecto_equipo", "actividad_orden"} & set(connection.introspection.table_names(cursor)):
            raise RuntimeError("Integration tables already exist; preserve and review")


def fill(apps, schema_editor):
    alias = schema_editor.connection.alias
    association = apps.get_model("proyectos", "ProjectTeam")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id,equipo_id FROM proyecto WHERE equipo_id IS NOT NULL")
        association.objects.using(alias).bulk_create([association(project_id=pk, team_id=team) for pk, team in cursor.fetchall()])
    order = apps.get_model("proyectos", "TaskOrder")
    positions = {}
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id,proyecto_id,padre_id FROM actividad ORDER BY proyecto_id,padre_id,id")
        while rows := cursor.fetchmany(500):
            batch = []
            for pk, project_id, parent_id in rows:
                key = project_id, parent_id
                positions[key] = positions.get(key, Decimal(0)) + 1024
                batch.append(order(task_id=pk, position=positions[key]))
            order.objects.using(alias).bulk_create(batch)
    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='actividad_etiqueta' AND CONSTRAINT_NAME='ck_actividad_etiqueta_clase'")
            if cursor.fetchone()[0]:
                cursor.execute("ALTER TABLE actividad_etiqueta DROP CHECK ck_actividad_etiqueta_clase")
            cursor.execute("ALTER TABLE actividad_etiqueta ADD CONSTRAINT ck_actividad_etiqueta_clase CHECK(clase IN ('technical','nontechnical','specialty'))")


def preserve(apps, schema_editor):
    raise RuntimeError("Integration rollback requires an explicit preservation plan for teams, specialties and manual order")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0012_task_detail"), ("organization", "0001_initial"), ("teams", "0001_initial")]
    operations = [
        migrations.RunPython(prepare, preserve),
        migrations.CreateModel(name="ProjectTeam", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("project", models.ForeignKey(to="proyectos.project", on_delete=django.db.models.deletion.CASCADE, db_constraint=False, db_column="proyecto_id")),
            ("team", models.ForeignKey(to="teams.team", on_delete=django.db.models.deletion.PROTECT, db_constraint=False, db_column="equipo_id")),
        ], options={"db_table": "proyecto_equipo", "constraints": [models.UniqueConstraint(fields=("project", "team"), name="uq_proyecto_equipo")]}),
        migrations.CreateModel(name="TaskOrder", fields=[
            ("task", models.OneToOneField(to="proyectos.task", primary_key=True, serialize=False, on_delete=django.db.models.deletion.CASCADE, db_constraint=False, db_column="actividad_id", related_name="manual_order")),
            ("position", models.DecimalField(max_digits=38, decimal_places=18, db_column="posicion")),
        ], options={"db_table": "actividad_orden"}),
        migrations.AddField(model_name="tasklabel", name="specialty", field=models.ForeignKey(to="organization.specialty", null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, db_constraint=False, db_column="especialidad_id")),
        migrations.RunPython(fill, preserve),
    ]
