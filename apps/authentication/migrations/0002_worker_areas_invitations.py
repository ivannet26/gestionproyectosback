import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def extend_worker(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        raise RuntimeError("Worker scope DDL requires MySQL; isolated tests create synthetic tables separately")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'trabajador' AND COLUMN_NAME = 'area_id'")
        definition = cursor.fetchone()
        if definition != ("bigint unsigned", "NO"):
            raise RuntimeError("Worker primary area differs from reviewed schema; inspect before migration")
        cursor.execute("SELECT COUNT(*) FROM usuario_rol WHERE rol_codigo NOT IN ('ADMINISTRADOR', 'COLABORADOR', 'TRABAJADOR')")
        if cursor.fetchone()[0]:
            raise RuntimeError("Unexpected global assignments require review before schema changes")
    schema_editor.execute("ALTER TABLE trabajador MODIFY area_id BIGINT UNSIGNED NULL, ADD COLUMN todas_las_areas BOOLEAN NOT NULL DEFAULT FALSE, ADD CONSTRAINT ck_trabajador_alcance CHECK ((todas_las_areas = 1 AND area_id IS NULL) OR (todas_las_areas = 0 AND area_id IS NOT NULL))")


def restore_worker(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("ALTER TABLE trabajador DROP CHECK ck_trabajador_alcance, DROP COLUMN todas_las_areas, MODIFY area_id BIGINT UNSIGNED NOT NULL")


def unsigned_relationships(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("ALTER TABLE trabajador_area MODIFY trabajador_id BIGINT UNSIGNED NOT NULL, MODIFY area_id BIGINT UNSIGNED NOT NULL")
        schema_editor.execute("ALTER TABLE trabajador_area ADD CONSTRAINT fk_trabajador_area_trabajador FOREIGN KEY (trabajador_id) REFERENCES trabajador(id) ON DELETE CASCADE, ADD CONSTRAINT fk_trabajador_area_area FOREIGN KEY (area_id) REFERENCES area(id)")


def remove_relationships(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("ALTER TABLE trabajador_area DROP FOREIGN KEY fk_trabajador_area_trabajador, DROP FOREIGN KEY fk_trabajador_area_area")


def guard_rollback(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM trabajador WHERE todas_las_areas = 1 OR area_id IS NULL")
        if cursor.fetchone()[0]:
            raise RuntimeError("Rollback requires an explicitly selected primary area for every worker")
        cursor.execute("SELECT COUNT(*) FROM trabajador_area ta JOIN trabajador t ON t.id = ta.trabajador_id WHERE ta.area_id <> t.area_id")
        if cursor.fetchone()[0]:
            raise RuntimeError("Rollback would remove additional worker areas; reconcile them first")
        cursor.execute("SELECT COUNT(*) FROM auth_invitation")
        if cursor.fetchone()[0]:
            raise RuntimeError("Rollback would remove invitation history; archive it before proceeding")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("autenticacion", "0001_initial")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(extend_worker, restore_worker)],
            state_operations=[
                migrations.AddField(model_name="worker", name="area", field=models.ForeignKey(db_column="area_id", null=True, on_delete=django.db.models.deletion.DO_NOTHING, to="autenticacion.area")),
                migrations.AddField(model_name="worker", name="all_areas", field=models.BooleanField(db_column="todas_las_areas", default=False)),
            ],
        ),
        migrations.CreateModel(
            name="WorkerArea",
            fields=[
                ("pk", models.CompositePrimaryKey("worker_id", "area_id", blank=True, editable=False, primary_key=True, serialize=False)),
                ("worker", models.ForeignKey(db_column="trabajador_id", db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to="autenticacion.worker")),
                ("area", models.ForeignKey(db_column="area_id", db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to="autenticacion.area")),
            ], options={"db_table": "trabajador_area"},
        ),
        migrations.RunPython(unsigned_relationships, remove_relationships),
        migrations.CreateModel(
            name="Invitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email_digest", models.CharField(max_length=64)),
                ("delivery_status", models.CharField(default="pending", max_length=16)),
                ("provider_message_id", models.CharField(blank=True, max_length=128)),
                ("last_attempt_at", models.DateTimeField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("token", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="autenticacion.authtoken")),
                ("created_by", models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name="issued_invitations", to=settings.AUTH_USER_MODEL)),
            ], options={"db_table": "auth_invitation"},
        ),
        migrations.CreateModel(
            name="MigrationBackup",
            fields=[("key", models.CharField(max_length=80, primary_key=True, serialize=False)), ("payload", models.JSONField())],
            options={"db_table": "auth_migration_backup"},
        ),
        migrations.RunPython(migrations.RunPython.noop, guard_rollback),
    ]
