import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("autenticacion", "0006_alter_workerarea_worker_delete_worker"),
        ("workers", "0001_existing_worker_models"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="WorkerArea"),
                migrations.AddField(
                    model_name="user",
                    name="worker",
                    field=models.OneToOneField(
                        db_column="trabajador_id",
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="workers.worker",
                    ),
                ),
            ],
        ),
    ]
