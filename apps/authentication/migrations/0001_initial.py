import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('username', models.CharField(db_column='nombre_usuario', max_length=80, unique=True)),
                ('password', models.CharField(db_column='password_hash', max_length=255)),
                ('is_active', models.BooleanField(db_column='activo')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='creado_en')),
            ],
            options={
                'db_table': 'usuario',
                'managed': False,
            },
        ),
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
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('code', models.CharField(db_column='codigo', max_length=24, primary_key=True, serialize=False)),
                ('name', models.CharField(db_column='nombre', max_length=80, unique=True)),
            ],
            options={
                'db_table': 'rol',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('pk', models.CompositePrimaryKey('user_id', 'role_code', blank=True, editable=False, primary_key=True, serialize=False)),
                ('role_code', models.CharField(db_column='rol_codigo', max_length=24)),
            ],
            options={
                'db_table': 'usuario_rol',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Worker',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(db_column='codigo', max_length=30, unique=True)),
                ('first_names', models.CharField(db_column='nombres', max_length=100)),
                ('last_names', models.CharField(db_column='apellidos', max_length=120)),
                ('email', models.EmailField(db_column='correo', max_length=254, null=True, unique=True)),
                ('active', models.BooleanField(db_column='activo')),
            ],
            options={
                'db_table': 'trabajador',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='AuthThrottle',
            fields=[
                ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('failures', models.PositiveIntegerField(default=0)),
                ('window_started_at', models.DateTimeField()),
                ('blocked_until', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'auth_throttle',
            },
        ),
        migrations.CreateModel(
            name='AuthToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('digest', models.CharField(max_length=64, unique=True)),
                ('purpose', models.CharField(choices=[('access', 'Access'), ('refresh', 'Refresh'), ('activation', 'Activation'), ('reset', 'Reset')], max_length=16)),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'auth_token',
                'indexes': [models.Index(fields=['user', 'purpose', 'consumed_at'], name='auth_token_user_id_61e2c4_idx')],
            },
        ),
        migrations.CreateModel(
            name='RecoveryRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_recoveries', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'auth_recovery_request',
                'indexes': [models.Index(fields=['resolved_at', 'requested_at'], name='auth_recove_resolve_e4fa45_idx')],
            },
        ),
    ]
