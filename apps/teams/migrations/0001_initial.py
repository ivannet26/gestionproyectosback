import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("organization", "0001_initial"),
        ("workers", "0001_existing_worker_models"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Team",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
                        (
                            "area",
                            models.ForeignKey(
                                db_column="area_id",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                to="organization.area",
                            ),
                        ),
                        ("name", models.CharField(db_column="nombre", max_length=120)),
                        ("active", models.BooleanField(db_column="activo", default=True)),
                    ],
                    options={"db_table": "equipo", "managed": False, "ordering": ["name"]},
                ),
                migrations.CreateModel(
                    name="TeamMember",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
                        (
                            "team",
                            models.ForeignKey(
                                db_column="equipo_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="members",
                                to="teams.team",
                            ),
                        ),
                        (
                            "worker",
                            models.ForeignKey(
                                db_column="trabajador_id",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                to="workers.worker",
                            ),
                        ),
                        ("joined_date", models.DateField(db_column="fecha_ingreso")),
                        (
                            "left_date",
                            models.DateField(blank=True, db_column="fecha_salida", null=True),
                        ),
                    ],
                    options={"db_table": "equipo_miembro", "managed": False, "ordering": ["id"]},
                ),
            ],
        ),
    ]
