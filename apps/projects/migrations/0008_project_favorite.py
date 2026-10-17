from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("proyectos", "0007_project_single_area"),
        ("autenticacion", "0007_worker_area_ownership"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectFavorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(
                    to="autenticacion.user", on_delete=django.db.models.deletion.CASCADE,
                    db_constraint=False, db_column="usuario_id",
                )),
                ("project", models.ForeignKey(
                    to="proyectos.project", on_delete=django.db.models.deletion.CASCADE,
                    db_constraint=False, db_column="proyecto_id",
                )),
            ],
            options={
                "db_table": "proyecto_favorito",
                "constraints": [models.UniqueConstraint(
                    fields=("user", "project"), name="uq_proyecto_favorito_usuario",
                )],
            },
        ),
    ]
