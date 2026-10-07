import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('autenticacion', '0004_global_admin_sql_policy'),
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(db_column='codigo', max_length=40, unique=True)),
                ('name', models.CharField(db_column='nombre', max_length=180)),
                ('description', models.TextField(db_column='descripcion', null=True)),
                ('type_code', models.CharField(db_column='tipo_codigo', max_length=30)),
                ('state_code', models.CharField(db_column='estado_codigo', default='PLANIFICADO', max_length=20)),
                ('priority', models.PositiveSmallIntegerField(db_column='prioridad', default=3)),
                ('start_date', models.DateField(db_column='fecha_inicio', null=True)),
                ('end_date', models.DateField(db_column='fecha_fin', null=True)),
                ('confidential', models.BooleanField(db_column='confidencial', default=False)),
                ('archived', models.BooleanField(db_column='archivado', default=False)),
                ('available', models.BooleanField(db_column='disponible_por_area', default=False)),
                ('worker_edit', models.BooleanField(db_column='trabajador_edita_tareas', default=False)),
                ('worker_state', models.BooleanField(db_column='trabajador_cambia_estado', default=False)),
                ('created_at', models.DateTimeField(db_column='creado_en', default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(db_column='actualizado_en', default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'proyecto',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ProjectMember',
            fields=[
                ('pk', models.CompositePrimaryKey('project_id', 'worker_id', blank=True, editable=False, primary_key=True, serialize=False)),
                ('project_role', models.CharField(db_column='rol_proyecto', default='COLABORADOR', max_length=20)),
                ('active', models.BooleanField(db_column='activo', default=True)),
            ],
            options={
                'db_table': 'proyecto_miembro',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ProjectState',
            fields=[
                ('code', models.CharField(db_column='codigo', max_length=20, primary_key=True, serialize=False)),
                ('name', models.CharField(db_column='nombre', max_length=70)),
                ('terminal', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'estado_proyecto',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ProjectType',
            fields=[
                ('code', models.CharField(db_column='codigo', max_length=30, primary_key=True, serialize=False)),
                ('name', models.CharField(db_column='nombre', max_length=100)),
            ],
            options={
                'db_table': 'tipo_proyecto',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('phase_id', models.PositiveBigIntegerField(db_column='fase_id', null=True)),
                ('name', models.CharField(db_column='nombre', max_length=180)),
                ('state_code', models.CharField(db_column='estado_codigo', max_length=20)),
                ('priority', models.PositiveSmallIntegerField(db_column='prioridad', default=3)),
                ('start_date', models.DateField(db_column='fecha_inicio')),
                ('due_date', models.DateField(db_column='fecha_fin')),
                ('progress', models.DecimalField(db_column='avance', decimal_places=2, default=0, max_digits=5)),
                ('reason', models.CharField(db_column='motivo_cambio', max_length=500, null=True)),
                ('archived', models.BooleanField(db_column='archivada', default=False)),
                ('created_at', models.DateTimeField(db_column='creado_en', default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(db_column='actualizado_en', default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'actividad',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='TaskDependency',
            fields=[
                ('pk', models.CompositePrimaryKey('project_id', 'predecessor_id', 'successor_id', blank=True, editable=False, primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'dependencia_actividad',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='TaskState',
            fields=[
                ('code', models.CharField(db_column='codigo', max_length=20, primary_key=True, serialize=False)),
                ('name', models.CharField(db_column='nombre', max_length=70)),
                ('terminal', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'estado_actividad',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='TaskTransition',
            fields=[
                ('pk', models.CompositePrimaryKey('source', 'target', blank=True, editable=False, primary_key=True, serialize=False)),
                ('source', models.CharField(db_column='origen', max_length=20)),
                ('target', models.CharField(db_column='destino', max_length=20)),
                ('supervision_required', models.BooleanField(db_column='requiere_supervision', default=False)),
                ('reason_required', models.BooleanField(db_column='requiere_motivo', default=False)),
            ],
            options={
                'db_table': 'transicion_actividad',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ProjectArea',
            fields=[
                ('pk', models.CompositePrimaryKey('project_id', 'area_id', blank=True, editable=False, primary_key=True, serialize=False)),
                ('area', models.ForeignKey(db_column='area_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='autenticacion.area')),
                ('project', models.ForeignKey(db_column='proyecto_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='proyectos.project')),
            ],
            options={
                'db_table': 'proyecto_area',
            },
        ),
        migrations.CreateModel(
            name='ProjectRequirement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_column='nombre', max_length=120)),
                ('kind', models.CharField(db_column='clase', max_length=20)),
                ('project', models.ForeignKey(db_column='proyecto_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='proyectos.project')),
            ],
            options={
                'db_table': 'proyecto_requisito',
            },
        ),
        migrations.CreateModel(
            name='TaskLabel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_column='nombre', max_length=120)),
                ('kind', models.CharField(db_column='clase', max_length=20)),
                ('requirement', models.ForeignKey(db_column='requisito_id', null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='proyectos.projectrequirement')),
                ('task', models.ForeignKey(db_column='actividad_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='proyectos.task')),
            ],
            options={
                'db_table': 'actividad_etiqueta',
            },
        ),
        migrations.AddConstraint(
            model_name='projectrequirement',
            constraint=models.UniqueConstraint(fields=('project', 'name', 'kind'), name='uq_proyecto_requisito'),
        ),
        migrations.AddConstraint(
            model_name='tasklabel',
            constraint=models.UniqueConstraint(fields=('task', 'name', 'kind'), name='uq_actividad_etiqueta'),
        ),
    ]
