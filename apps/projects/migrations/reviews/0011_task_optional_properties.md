# Creación rápida: propiedades opcionales

## Contrato

Se conserva `POST /api/projects/{id}/tasks/`. `name` y el `state_code` técnico siguen validados; la interfaz resuelve el estado desde la configuración del proyecto. El nombre se recorta. La creación acepta omitir `due_date` y `priority`, o enviarlos como `null`: ambos se almacenan realmente vacíos. Los valores informados conservan su formato, rango y límites de proyecto/padre. En PATCH, omitir conserva el valor y `null` lo limpia. `start_date` sigue siendo obligatoria internamente y procede del padre o del inicio del proyecto, según la regla existente; no se fabrica una fecha límite.

Los responsables y etiquetas siguen siendo opcionales. El administrador puede crear sin responsable. El trabajador conserva la autoasignación existente, exclusivamente con permiso efectivo de creación y participación activa. La edición no concede creación ni cambio de estado. Se conservan los requisitos de responsable y motivo de cada estado; la fila rápida utiliza el estado inicial configurado e informa del cambio cuando el grupo exige datos adicionales. La asignación y las etiquetas siguen usando los servicios actuales; no hay otro endpoint de persistencia.

El formulario completo conserva sus valores iniciales anteriores para tareas nuevas (prioridad normal y fecha del contexto si existe), pero permite limpiarlos y no rellena valores vacíos de una tarea existente.

## Necesidad e impacto de 0011

El modelo/esquema histórico declara `actividad.fecha_fin` y `actividad.prioridad` no nulos; el procedimiento estructural 0010 exige una fecha final y el trigger compara fechas mediante `<>`, que no detecta transiciones desde/hacia NULL. Por ello no basta con quitar validaciones de React.

0011 hace ambas columnas anulables, preservando tipo físico y default previo; no cambia valores existentes, claves ni índices. Mantiene la fecha inicial y valida fechas presentes, incluidas subtareas sin fecha final cuyo inicio excedería una nueva fecha límite del padre. Actualiza únicamente `sp_validar_estructura_actividad` y `bu_actividad_estructura`, conservando definidor y sql_mode. No modifica el gestor de plantillas ni migraciones anteriores.

El preflight exige pausa de escrituras, tipos compatibles y las definiciones SQL revisadas; guarda las definiciones originales en MigrationBackup. Si detecta otro esquema, se detiene para revisión. Ante un fallo SQL restaura las rutinas originales; MySQL DDL no es transaccional, de modo que las columnas pueden quedar anulables y requieren revisar el backup antes del reintento. No se debe reactivar la aplicación con una migración parcial.

Para despliegue autorizado, tras backup y revisión del esquema real, detener escrituras y habilitar temporalmente `TASK_OPTIONAL_MIGRATION_MAINTENANCE=1` antes de ejecutar la migración `proyectos 0011`. Esta entrega no ejecuta migraciones contra Aiven ni bases compartidas. Coordinar backend y frontend: el frontend nuevo requiere este contrato. El rollback se bloquea si existen tareas sin prioridad o fecha final; no inventa valores ni borra tareas para permitirlo.

## Verificación reproducible

SQLite explícito (reglas Python/HTTP, no procedimientos MySQL):

```powershell
$env:AUTH_TEST_SQLITE='1'
./.venv/Scripts/python.exe manage.py test apps.projects.tests.test_quick_tasks apps.projects.tests.test_task_inline apps.projects.tests.test_projects apps.projects.tests.test_assignees apps.projects.tests.test_task_states apps.projects.tests.test_state_templates apps.projects.tests.test_performance --noinput
./.venv/Scripts/python.exe manage.py check
./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```

MySQL 8.4 nuevo, temporal, local y sintético:

```powershell
./scripts/verify_task_status_mysql.ps1 -TestModule apps.projects.tests.test_quick_tasks_mysql
```

El script genera credenciales solo en memoria, crea `gm_test_task_status_templates` exclusivamente en su nuevo contenedor y lo elimina al terminar. No usa conexiones existentes. Las pruebas aplican 0010 y 0011 sobre un esquema sintético controlado, ejercitan el procedimiento real y los triggers, prueban campos opcionales, permisos independientes, 16 combinaciones, límites de fechas y bloqueo/restauración del rollback. Esto no reemplaza el preflight del esquema real.

## Archivos

Se modifican `apps/projects/models.py`, `serializers.py`, `services/tasks.py` y las expectativas del contrato anterior en `tests/test_projects.py` y `tests/test_task_inline.py`. Se añaden `tests/test_quick_tasks.py`, `tests/test_quick_tasks_mysql.py`, la migración `0011_task_optional_properties.py` y sus dos archivos SQL. `scripts/verify_task_status_mysql.ps1` permite seleccionar el módulo aislado de pruebas y `.env.example` documenta el indicador de mantenimiento; no se modifica `.env`.
