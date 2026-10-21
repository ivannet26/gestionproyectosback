from importlib import import_module

from django.db import DatabaseError, migrations


previous = import_module("apps.projects.migrations.0014_task_direct_move")
helpers = previous.baseline.helpers
KEY = "task_state_without_assignee_0015"


def source():
    original = previous.source()
    requirement = """  IF v_responsable IS NULL OR NOT EXISTS(SELECT 1 FROM proyecto_miembro pm JOIN trabajador t ON t.id=pm.trabajador_id
   WHERE pm.proyecto_id=p_proyecto AND pm.trabajador_id=v_responsable AND pm.activo=1 AND t.activo=1) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La actividad debe tener un responsable activo del proyecto.';
  END IF;
"""
    if original.count(requirement) != 1:
        raise RuntimeError("Task assignee policy requires review")
    return original.replace(requirement, "", 1)


def install(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    previous.maintained(connection)
    with connection.cursor() as cursor:
        original = helpers.read_definition(cursor, "PROCEDURE", previous.MODE)
        if previous.baseline.normalized(original["Create Procedure"]) != previous.baseline.normalized(previous.source()):
            raise RuntimeError("Task routine differs from reviewed baseline; preserve and review")
        backup = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias)
        saved, created = backup.get_or_create(key=KEY, defaults={"payload": original})
        if not created and saved.payload != original:
            raise RuntimeError("Task assignee policy backup differs; preserve and review")
        try:
            helpers.recreate(cursor, previous.MODE, previous.with_definer(source(), original["Create Procedure"]), original)
        except (DatabaseError, RuntimeError):
            helpers.recreate(cursor, previous.MODE, original["Create Procedure"], original)
            raise


def restore(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    previous.maintained(connection)
    with connection.cursor() as cursor:
        current = helpers.read_definition(cursor, "PROCEDURE", previous.MODE)
        if previous.baseline.normalized(current["Create Procedure"]) != previous.baseline.normalized(source()):
            raise RuntimeError("Task state routine changed; preserve and review")
        saved = apps.get_model("autenticacion", "MigrationBackup").objects.using(connection.alias).get(key=KEY)
        helpers.recreate(cursor, previous.MODE, saved.payload["Create Procedure"], saved.payload)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("proyectos", "0014_task_direct_move")]
    operations = [migrations.RunPython(install, restore)]
