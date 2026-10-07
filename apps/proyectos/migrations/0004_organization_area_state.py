import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proyectos", "0003_project_sql_policy"),
        ("organization", "0001_initial"),
    ]
    run_before = [("autenticacion", "0005_alter_workerarea_area_delete_area")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="projectarea",
                    name="area",
                    field=models.ForeignKey(
                        db_column="area_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="organization.area",
                    ),
                ),
            ],
        ),
    ]
