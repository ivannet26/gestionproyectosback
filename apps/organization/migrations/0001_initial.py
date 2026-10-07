from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Area',
                    fields=[
                        ('id', models.BigAutoField(primary_key=True, serialize=False)),
                        ('code', models.CharField(db_column='codigo', max_length=30, unique=True)),
                        ('name', models.CharField(db_column='nombre', max_length=120, unique=True)),
                        ('active', models.BooleanField(db_column='activa')),
                    ],
                    options={
                        'db_table': 'area',
                        'ordering': ['name'],
                        'managed': False,
                    },
                ),
                migrations.CreateModel(
                    name='Specialty',
                    fields=[
                        ('id', models.BigAutoField(primary_key=True, serialize=False)),
                        ('name', models.CharField(db_column='nombre', max_length=120, unique=True)),
                    ],
                    options={
                        'db_table': 'especialidad',
                        'ordering': ['name'],
                        'managed': False,
                    },
                ),
            ],
        ),
    ]
