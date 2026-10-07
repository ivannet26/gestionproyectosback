from importlib import import_module

from django.db import migrations


BACKUP_KEY = "project_schema_0002"
FLAGS = ("disponible_por_area", "trabajador_edita_tareas", "trabajador_cambia_estado")


def constraint_exists(cursor, table, name):
    cursor.execute("SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME=%s AND CONSTRAINT_NAME=%s", [table, name])
    return bool(cursor.fetchone()[0])


def nullable(cursor, table, column):
    cursor.execute("SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s", [table, column])
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Required legacy column is missing; review schema")
    return row[0] == "YES"


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    policy = import_module("apps.proyectos.migrations.0003_project_sql_policy")
    with schema_editor.connection.cursor() as cursor:
        definitions = policy.review(cursor)
        if policy.view_body(definitions["view"]["Create View"]) != policy.view_body(policy.source(policy.VIEW, True)):
            raise RuntimeError("SQL view differs from reviewed baseline; review before schema changes")
        if not backup.objects.using(alias).filter(key=BACKUP_KEY).exists():
            if nullable(cursor, "proyecto", "fecha_inicio") or nullable(cursor, "proyecto", "fecha_fin") or nullable(cursor, "actividad", "fase_id"):
                raise RuntimeError("Legacy nullability differs from baseline; review schema")
            cursor.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto' AND COLUMN_NAME IN ('disponible_por_area','trabajador_edita_tareas','trabajador_cambia_estado')")
            if cursor.fetchone()[0]:
                raise RuntimeError("Project permissions already exist; review schema")
            cursor.execute("SELECT COUNT(*) FROM tipo_proyecto WHERE codigo='GENERAL'")
            backup.objects.using(alias).create(key=BACKUP_KEY, payload={"general_existed": bool(cursor.fetchone()[0])})
        cursor.execute("ALTER TABLE proyecto MODIFY fecha_inicio DATE NULL, MODIFY fecha_fin DATE NULL")
        for flag in FLAGS:
            cursor.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='proyecto' AND COLUMN_NAME=%s", [flag])
            if not cursor.fetchone()[0]:
                cursor.execute(f"ALTER TABLE proyecto ADD COLUMN {flag} BOOLEAN NOT NULL DEFAULT FALSE, ADD CONSTRAINT ck_proyecto_{flag} CHECK ({flag} IN (0,1))")
        for name in ("fk_actividad_27", "fk_actividad_28"):
            if constraint_exists(cursor, "actividad", name):
                cursor.execute(f"ALTER TABLE actividad DROP FOREIGN KEY {name}")
        cursor.execute("ALTER TABLE actividad MODIFY fase_id BIGINT UNSIGNED NULL")
        cursor.execute("ALTER TABLE actividad ADD CONSTRAINT fk_actividad_27 FOREIGN KEY (proyecto_id,fase_id) REFERENCES fase(proyecto_id,id), ADD CONSTRAINT fk_actividad_28 FOREIGN KEY (proyecto_id,fase_id,padre_id) REFERENCES actividad(proyecto_id,fase_id,id)")
        if not constraint_exists(cursor, "actividad", "fk_actividad_padre_proyecto"):
            cursor.execute("ALTER TABLE actividad ADD CONSTRAINT fk_actividad_padre_proyecto FOREIGN KEY (proyecto_id,padre_id) REFERENCES actividad(proyecto_id,id)")
        specifications = (
            ("proyecto_area", "proyecto_id", "proyecto", "fk_proyecto_area_proyecto"),
            ("proyecto_area", "area_id", "area", "fk_proyecto_area_area"),
            ("proyecto_requisito", "proyecto_id", "proyecto", "fk_proyecto_requisito_proyecto"),
            ("actividad_etiqueta", "actividad_id", "actividad", "fk_actividad_etiqueta_actividad"),
        )
        for table, column, target, name in specifications:
            if not constraint_exists(cursor, table, name):
                cursor.execute(f"ALTER TABLE {table} MODIFY {column} BIGINT UNSIGNED NOT NULL, ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES {target}(id)")
        for table in ("proyecto_requisito", "actividad_etiqueta"):
            name = f"ck_{table}_clase"
            if not constraint_exists(cursor, table, name):
                cursor.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (clase IN ('technical','nontechnical'))")
        cursor.execute("INSERT INTO tipo_proyecto(codigo,nombre) SELECT 'GENERAL','General' WHERE NOT EXISTS(SELECT 1 FROM tipo_proyecto WHERE codigo='GENERAL')")
        cursor.execute("INSERT INTO proyecto_area(proyecto_id,area_id) SELECT p.id,p.area_id FROM proyecto p WHERE NOT EXISTS(SELECT 1 FROM proyecto_area pa WHERE pa.proyecto_id=p.id AND pa.area_id=p.area_id)")


def ensure_unused(cursor):
    checks = (
        "SELECT EXISTS(SELECT 1 FROM proyecto WHERE fecha_inicio IS NULL OR fecha_fin IS NULL OR disponible_por_area=1 OR trabajador_edita_tareas=1 OR trabajador_cambia_estado=1 OR tipo_codigo='GENERAL')",
        "SELECT EXISTS(SELECT 1 FROM actividad WHERE fase_id IS NULL)",
        "SELECT EXISTS(SELECT 1 FROM proyecto_area pa JOIN proyecto p ON p.id=pa.proyecto_id WHERE pa.area_id<>p.area_id)",
        "SELECT EXISTS(SELECT 1 FROM proyecto_requisito)",
        "SELECT EXISTS(SELECT 1 FROM actividad_etiqueta)",
    )
    for statement in checks:
        cursor.execute(statement)
        if cursor.fetchone()[0]:
            raise RuntimeError("Project flow contains new data; rollback requires explicit preservation plan")


def restore(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    backup = apps.get_model("autenticacion", "MigrationBackup")
    saved = backup.objects.using(schema_editor.connection.alias).get(key=BACKUP_KEY)
    with schema_editor.connection.cursor() as cursor:
        ensure_unused(cursor)
        cursor.execute("ALTER TABLE actividad DROP FOREIGN KEY fk_actividad_27, DROP FOREIGN KEY fk_actividad_28, DROP FOREIGN KEY fk_actividad_padre_proyecto")
        cursor.execute("ALTER TABLE actividad MODIFY fase_id BIGINT UNSIGNED NOT NULL, ADD CONSTRAINT fk_actividad_27 FOREIGN KEY (proyecto_id,fase_id) REFERENCES fase(proyecto_id,id), ADD CONSTRAINT fk_actividad_28 FOREIGN KEY (proyecto_id,fase_id,padre_id) REFERENCES actividad(proyecto_id,fase_id,id)")
        cursor.execute("ALTER TABLE proyecto MODIFY fecha_inicio DATE NOT NULL, MODIFY fecha_fin DATE NOT NULL")
        for flag in FLAGS:
            cursor.execute(f"ALTER TABLE proyecto DROP CHECK ck_proyecto_{flag}, DROP COLUMN {flag}")
        if not saved.payload["general_existed"]:
            cursor.execute("DELETE FROM tipo_proyecto WHERE codigo='GENERAL'")
    saved.delete()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0001_initial")]
    operations = [migrations.RunPython(install, restore)]
