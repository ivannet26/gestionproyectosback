import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("organization", "0001_initial"),
        ("autenticacion", "0005_alter_workerarea_area_delete_area"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Worker",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
                        ("area", models.ForeignKey(blank=True, db_column="area_id", null=True, on_delete=django.db.models.deletion.DO_NOTHING, to="organization.area")),
                        ("code", models.CharField(db_column="codigo", max_length=30, unique=True)),
                        ("first_names", models.CharField(db_column="nombres", max_length=100)),
                        ("last_names", models.CharField(db_column="apellidos", max_length=120)),
                        ("email", models.EmailField(blank=True, db_column="correo", max_length=254, null=True, unique=True)),
                        ("weekly_hours", models.DecimalField(blank=True, db_column="horas_semanales", decimal_places=2, max_digits=5, null=True)),
                        ("active", models.BooleanField(db_column="activo", default=True)),
                        ("all_areas", models.BooleanField(db_column="todas_las_areas", default=False)),
                        ("specialties", models.ManyToManyField(related_name="workers", through="workers.WorkerSpecialty", to="organization.specialty")),
                    ],
                    options={"db_table": "trabajador", "managed": False},
                ),
                migrations.CreateModel(
                    name="WorkerArea",
                    fields=[
                        ("pk", models.CompositePrimaryKey("worker_id", "area_id", blank=True, editable=False, primary_key=True, serialize=False)),
                        ("worker", models.ForeignKey(db_column="trabajador_id", db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to="workers.worker")),
                        ("area", models.ForeignKey(db_column="area_id", db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to="organization.area")),
                    ],
                    options={"db_table": "trabajador_area"},
                ),
                migrations.CreateModel(
                    name="WorkerSpecialty",
                    fields=[
                        ("pk", models.CompositePrimaryKey("worker", "specialty", blank=True, editable=False, primary_key=True, serialize=False)),
                        ("worker", models.ForeignKey(db_column="trabajador_id", on_delete=django.db.models.deletion.CASCADE, related_name="worker_specialties", to="workers.worker")),
                        ("specialty", models.ForeignKey(db_column="especialidad_id", on_delete=django.db.models.deletion.CASCADE, related_name="worker_specialties", to="organization.specialty")),
                        ("level", models.PositiveSmallIntegerField(db_column="nivel", default=1)),
                    ],
                    options={"db_table": "trabajador_especialidad", "managed": False},
                ),
            ],
        ),
    ]
