from django.db import migrations, models


ADD_PERMISSION_SQL = (
    "ALTER TABLE proyecto ADD COLUMN trabajador_crea_tareas BOOLEAN NOT NULL DEFAULT FALSE, "
    "ADD CONSTRAINT ck_proyecto_trabajador_crea_tareas CHECK (trabajador_crea_tareas IN (0,1))"
)
REMOVE_PERMISSION_SQL = (
    "ALTER TABLE proyecto DROP CHECK ck_proyecto_trabajador_crea_tareas, "
    "DROP COLUMN trabajador_crea_tareas"
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(ADD_PERMISSION_SQL)


def restore(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT 1 FROM proyecto WHERE trabajador_crea_tareas=1)")
        if cursor.fetchone()[0]:
            raise RuntimeError("Creation permissions are in use; preserve them before rollback")
        cursor.execute(REMOVE_PERMISSION_SQL)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0004_organization_area_state")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install, restore)],
            state_operations=[
                migrations.AddField(
                    model_name="project",
                    name="worker_create",
                    field=models.BooleanField(default=False, db_column="trabajador_crea_tareas"),
                ),
            ],
        ),
    ]
