from uuid import uuid4

from django.db import migrations, transaction


def transition(apps, schema_editor):
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    with transaction.atomic(using=alias), schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM usuario_rol WHERE rol_codigo NOT IN ('ADMINISTRADOR', 'COLABORADOR', 'TRABAJADOR')")
        if cursor.fetchone()[0]:
            raise RuntimeError("Unexpected legacy global assignments require explicit review before migration")
        cursor.execute("SELECT codigo, nombre FROM rol")
        catalog = list(cursor.fetchall())
        cursor.execute("SELECT usuario_id, rol_codigo FROM usuario_rol")
        assignments = list(cursor.fetchall())
        cursor.execute("SELECT t.id, t.area_id FROM trabajador t WHERE t.todas_las_areas = 0 AND t.area_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM trabajador_area ta WHERE ta.trabajador_id = t.id AND ta.area_id = t.area_id)")
        areas = list(cursor.fetchall())
        backup.objects.using(alias).create(key="roles_and_areas_0003", payload={"catalog": catalog, "assignments": assignments, "areas": areas})
        if not any(code == "TRABAJADOR" for code, _ in catalog):
            cursor.execute("INSERT INTO rol (codigo, nombre) VALUES (%s, %s)", ["TRABAJADOR", f"Transicion-{uuid4().hex}"])
        admin_ids = {user_id for user_id, code in assignments if code == "ADMINISTRADOR"}
        worker_ids = {user_id for user_id, code in assignments if code in ("COLABORADOR", "TRABAJADOR")} - admin_ids
        existing_worker_ids = {user_id for user_id, code in assignments if code == "TRABAJADOR"}
        if worker_ids - existing_worker_ids:
            cursor.executemany("INSERT INTO usuario_rol (usuario_id, rol_codigo) VALUES (%s, %s)", [(user_id, "TRABAJADOR") for user_id in worker_ids - existing_worker_ids])
        cursor.execute("DELETE FROM usuario_rol WHERE rol_codigo = 'COLABORADOR'")
        if admin_ids & existing_worker_ids:
            cursor.executemany("DELETE FROM usuario_rol WHERE usuario_id = %s AND rol_codigo = 'TRABAJADOR'", [(user_id,) for user_id in admin_ids & existing_worker_ids])
        cursor.execute("DELETE FROM rol WHERE codigo NOT IN ('ADMINISTRADOR', 'TRABAJADOR')")
        if not any(code == "ADMINISTRADOR" and name.casefold() == "trabajador" for code, name in catalog):
            cursor.execute("UPDATE rol SET nombre = %s WHERE codigo = 'TRABAJADOR'", ["Trabajador"])
        if areas:
            cursor.executemany("INSERT INTO trabajador_area (trabajador_id, area_id) VALUES (%s, %s)", areas)


def restore(apps, schema_editor):
    backup = apps.get_model("autenticacion", "MigrationBackup")
    alias = schema_editor.connection.alias
    saved = backup.objects.using(alias).get(key="roles_and_areas_0003")
    catalog = saved.payload["catalog"]
    assignments = saved.payload["assignments"]
    original_ids = {user_id for user_id, _ in assignments}
    with transaction.atomic(using=alias), schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT usuario_id, rol_codigo FROM usuario_rol")
        current = list(cursor.fetchall())
        if "TRABAJADOR" not in {code for code, _ in catalog} and any(user_id not in original_ids and code == "TRABAJADOR" for user_id, code in current):
            raise RuntimeError("New worker accounts depend on TRABAJADOR; review them before rollback")
        admin_ids = {user_id for user_id, role in assignments if role == "ADMINISTRADOR"}
        expected = {(user_id, "ADMINISTRADOR" if user_id in admin_ids else "TRABAJADOR") for user_id in original_ids}
        if {(user_id, code) for user_id, code in current if user_id in original_ids} != expected:
            raise RuntimeError("Role assignments changed after migration; review rollback")
        cursor.execute("UPDATE rol SET nombre = %s WHERE codigo = 'TRABAJADOR'", [f"Transicion-{uuid4().hex}"])
        for code, name in catalog:
            cursor.execute("SELECT COUNT(*) FROM rol WHERE codigo = %s", [code])
            if not cursor.fetchone()[0]:
                cursor.execute("INSERT INTO rol (codigo, nombre) VALUES (%s, %s)", [code, name])
            elif code == "TRABAJADOR":
                cursor.execute("UPDATE rol SET nombre = %s WHERE codigo = %s", [name, code])
        for user_id in original_ids:
            cursor.execute("DELETE FROM usuario_rol WHERE usuario_id = %s", [user_id])
        if assignments:
            cursor.executemany("INSERT INTO usuario_rol (usuario_id, rol_codigo) VALUES (%s, %s)", assignments)
        if "TRABAJADOR" not in {code for code, _ in catalog}:
            cursor.execute("DELETE FROM rol WHERE codigo = 'TRABAJADOR'")
        if saved.payload["areas"]:
            cursor.executemany("DELETE FROM trabajador_area WHERE trabajador_id = %s AND area_id = %s", saved.payload["areas"])
        saved.delete()


def enforce_final_catalog(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("ALTER TABLE rol ADD CONSTRAINT ck_rol_global CHECK (codigo IN ('ADMINISTRADOR', 'TRABAJADOR'))")


def release_final_catalog(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("ALTER TABLE rol DROP CHECK ck_rol_global")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("autenticacion", "0002_worker_areas_invitations")]
    operations = [migrations.RunPython(transition, restore), migrations.RunPython(enforce_final_catalog, release_final_catalog)]
