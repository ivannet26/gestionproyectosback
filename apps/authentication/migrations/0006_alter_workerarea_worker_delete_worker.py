import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('autenticacion', '0005_alter_workerarea_area_delete_area'),
        ('workers', '0001_existing_worker_models'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='workerarea',
                    name='worker',
                    field=models.ForeignKey(db_column='trabajador_id', db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to='workers.worker'),
                ),
                migrations.DeleteModel(
                    name='Worker',
                ),
            ],
        ),
    ]
