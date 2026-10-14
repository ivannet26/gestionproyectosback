# 0007: proyecto.area_id como única fuente de verdad

## Auditoría y alcance

Las capturas entregadas por el responsable muestran cero filas en la auditoría de asociaciones faltantes, múltiples o distintas de `proyecto.area_id`. No hay proyectos afectados que identificar en ese resultado. La búsqueda de dependencias de Aiven reportó únicamente `sp_cambiar_estado_actividad`, sin vistas ni triggers. No se accedió a Aiven para esta entrega. Es una evidencia puntual: la migración repite la validación antes de modificar el esquema.

La búsqueda local abarcó modelos, serializers, servicios, permisos, vistas API, pruebas, migraciones y archivos SQL. Los directorios de `database/` no contienen archivos SQL. Las referencias activas estaban en `ProjectArea`, `project_areas`, `create_project`, `visible_projects` y el procedimiento de estados. Las referencias en migraciones y SQL históricos se conservan intactas porque son necesarias para reconstruir versiones anteriores.

`POST /api/projects/` mantiene `area_ids` con exactamente un identificador; la respuesta conserva `areas` como lista de un elemento. Creación, visibilidad y elegibilidad usan exclusivamente `Project.area_id`. La fecha final opcional mantiene su contrato. `WorkerArea`, `trabajador_area`, todas las áreas de un trabajador y sus permisos no cambian.

## Orden de despliegue preparado, no ejecutado en Aiven

1. Obtener un respaldo externo recuperable del esquema y datos; registrar `SHOW CREATE TABLE proyecto`, `SHOW CREATE TABLE proyecto_area` y `SHOW CREATE PROCEDURE sp_cambiar_estado_actividad`. Confirmar permisos de inspección completos: los metadatos pueden ocultar objetos ajenos. Revisar también consumidores externos, eventos, SQL dinámico y referencias desde otros esquemas, que una búsqueda textual no puede garantizar cubrir.
2. Detener todos los procesos que escriben proyectos o actividades, incluidos trabajadores de segundo plano y clientes SQL. Desplegar el código nuevo manteniendo detenidos esos procesos. No arrancar la versión nueva antes de completar la migración: ya no mantiene la tabla redundante. No volver a arrancar la versión anterior después de retirarla.
3. Inspeccionar el plan con `python manage.py migrate proyectos 0007_project_single_area --plan`. Confirmar que `proyectos.0006_task_descriptions_and_project_states` está aplicada; no volver a aplicarla ni modificarla. Establecer `PROJECT_AREA_MIGRATION_MAINTENANCE=1` únicamente en el proceso de migración, como confirmación operativa de que se detuvieron las escrituras. La variable no detiene escritores por sí sola.
4. En la ventana autorizada, ejecutar `python manage.py migrate proyectos 0007_project_single_area`. Este comando queda documentado para el operador; no se ejecutó en Aiven durante la implementación. La migración exige MySQL y verifica área NOT NULL, clave foránea a `area(id)`, áreas existentes, esquema de la tabla redundante, asociaciones exactas, referencias huérfanas y dependencias de rutinas, vistas, triggers, eventos y claves foráneas entrantes. Cualquier definición SQL no visible, dependencia adicional o procedimiento distinto de la versión revisada detiene la operación.
5. La migración guarda el `SHOW CREATE` original de tabla y procedimiento, metadatos y fase en `auth_migration_backup` bajo `project_single_area_0007`; sustituye el procedimiento por la versión `.0007.sql`, verifica su definición, vuelve a comprobar datos y dependencias, y finalmente ejecuta `DROP TABLE proyecto_area`. El estado Django elimina `ProjectArea` después de la operación física. Ejecutar las verificaciones posteriores y arrancar exclusivamente el código nuevo.

El procedimiento conserva firma, SQL SECURITY INVOKER, modo SQL previo y todas sus comprobaciones de usuario, rol, proyecto vigente, responsable, participación, permiso, supervisión, motivo, estados habilitados, transiciones, jerarquía, dependencias y entregables. La única sustitución en el cuerpo es la comprobación de áreas: consulta `proyecto.area_id` contra `v_trabajador_area_autorizada`.

## Si aparecen discrepancias

La migración informa id, código, nombre, área principal, cantidad y áreas asociadas, y se detiene sin reconciliar ni borrar asociaciones. Resolver cada caso requiere una decisión de datos separada:

| Hallazgo | Tratamiento propuesto, sujeto a revisión y autorización |
| --- | --- |
| Sin asociación | Confirmar que `proyecto.area_id` representa el área correcta y evaluar participantes; preparar una corrección explícita de la asociación antes de volver a auditar. |
| Varias áreas | Revisar el área empresarial del proyecto y el impacto sobre visibilidad, responsables y participantes. Decidir el área única por proyecto; preservar evidencia y aprobar por separado cualquier ajuste de relaciones. |
| Una asociación distinta de la principal | Determinar cuál refleja el área autorizada del proyecto; corregir explícitamente el dato equivocado con su auditoría y revisar permisos antes de reintentar. |
| Asociación huérfana o área principal inexistente | Investigar integridad y procedencia; preservar los registros y preparar una reparación específica. |

No se propone ni ejecuta una limpieza global automática. La evidencia adjunta no requiere actualmente ninguno de estos tratamientos.

## Fallos, reintentos y reversión

MySQL realiza commits implícitos en DDL. La migración es `atomic=False` y exige mantenimiento. Si la creación o verificación del procedimiento falla, intenta restaurar la definición original antes de propagar el error; no retira la tabla. Si la restauración también falla o el proceso termina entre DROP PROCEDURE y CREATE PROCEDURE, mantener el servicio detenido, inspeccionar `SHOW CREATE` y el respaldo, y preparar la recuperación explícita del procedimiento antes del reintento.

Una ejecución detenida después de instalar el procedimiento conserva la tabla y el checkpoint. Un reintento vuelve a validar el estado y los datos. Si se interrumpe después del DROP TABLE, admite únicamente un checkpoint propio y un procedimiento actualizado verificado, y completa el registro de fase. Una tabla ausente sin checkpoint, una tabla reaparecida después del checkpoint final o una definición desconocida se rechazan. No usar `--fake`.

La migración es deliberadamente irreversible mediante `migrate` hacia atrás: no reconstruye asociaciones ni ejecuta automáticamente SQL histórico. Si se requiere volver a la versión anterior, mantener las escrituras detenidas y preparar una recuperación versionada a partir del respaldo externo y de los cambios posteriores. El JSON de MigrationBackup conserva definiciones, no sustituye una copia de seguridad de datos.

## Verificación posterior de solo lectura

Las consultas están en `sql/verify_project_single_area.0007.sql`. Se espera: migración aplicada una vez, tabla redundante ausente, cero proyectos sin área válida, columna NOT NULL con clave foránea, procedimiento INVOKER sin referencia a `proyecto_area`, ninguna dependencia residual visible y checkpoint `table_removed`. Comparar el conteo de `trabajador_area` y los proyectos con los valores registrados antes del mantenimiento. No se modifica esa tabla.

## Pruebas reproducibles

### Corrección contrastada con el SQL de referencia

Se localizó y leyó `Sistema_G.Proyectos/BD/GM_Gestor_Proyectos_MySQL_Estructura_Actualizado.sql`. En la definición de `proyecto_area` las columnas físicas son `area_id`, `proyecto_id`; su clave primaria es `(proyecto_id, area_id)`. El orden de declaración de columnas no representa una diferencia de integridad. `review_schema()` ahora ordena la consulta por `COLUMN_NAME` y compara exactamente `(("area_id",), ("proyecto_id",))`, por lo que acepta ambos órdenes físicos y sigue rechazando cualquier columna adicional o faltante.

El fixture funcional declara ahora las columnas en el orden real. Se añadió `apps/projects/tests/project_single_area_reference.sql` con las definiciones de `area`, `cliente`, `tipo_proyecto`, `estado_proyecto`, `proyecto` y `proyecto_area` del archivo de referencia. Solo se retiraron los contadores AUTO_INCREMENT del volcado; se conservan orden físico, tipos, índices, claves foráneas, valores predeterminados, CHECK e InnoDB/utf8mb4_0900_ai_ci. No se copiaron datos del volcado. Una clase MySQL independiente aplica y registra 0007 sobre ese DDL con datos sintéticos y verifica conservación del área y fecha final NULL, actualización del procedimiento y retirada de la tabla.

La revisión encontró estas otras diferencias del fixture generado por Django: claves BIGINT con signo frente a UNSIGNED; nombres y cantidad de índices y claves foráneas; columnas adicionales y CHECK de `proyecto`, incluidos `cliente_id`, `motivo_cambio`, fecha final nullable y estado predeterminado BORRADOR; columnas generadas y ENUM de `proyecto_miembro`; `trabajador.horas_semanales` NOT NULL con valor predeterminado 40; y restricciones de hash de `usuario`. Las seis tablas del nuevo fixture de referencia cubren exactamente las estructuras que inspecciona o retira 0007, incluidos los tipos UNSIGNED y las restricciones de `proyecto`. Los fixtures funcionales de otros dominios siguen siendo sintéticos, incluida la vista mínima de entregables; no se afirma que reproduzcan todo el volcado. No se modificaron modelos o reglas de negocio para ajustar las pruebas.

La definición completa de `sp_cambiar_estado_actividad` del SQL de referencia coincide con `.0006.sql`, omitiendo únicamente la cláusula DEFINER y el delimitador del volcado al comparar. No se detectó otra suposición que impida esta corrección de 0007. La validación de metadatos y dependencias sigue ejecutándose antes del DDL al aplicar la migración.

Se utilizó MySQL Community 8.0.46 instalado localmente, inicializado con un directorio temporal nuevo y enlazado únicamente a `127.0.0.1:33379`. `config.settings_test_mysql` fija host loopback, base sintética `gm_test_single_area` y usuario local; no toma la conexión de Aiven. Requiere `GM_TEST_MYSQL_PORT` y, si corresponde, `GM_TEST_MYSQL_PASSWORD`. El conjunto rechaza una base que ya tenga tablas antes de preparar sus fixtures.

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings_test_mysql'
$env:GM_TEST_MYSQL_PORT='33379'
python manage.py test apps.projects.tests.test_project_single_area_mysql --verbosity 2
```

Los fixtures son sintéticos: tablas generadas desde los modelos, tabla histórica de asociaciones con claves foráneas, vista autorizada real y procedimiento completo de 0006, luego aplicación y registro reales de 0007 mediante `MigrationExecutor`, partiendo del estado histórico sintético. No se usa `--fake`. Los estados de entregables usan una vista sintética mínima para verificar el bloqueo; no se simula una copia completa de Aiven. Se probaron creación vía API, fecha opcional, visibilidad, asignaciones, trabajadores multiárea, ejecución real del procedimiento, restricciones conservadas, datos incompatibles, dependencias imprevistas, fallo de instalación, reintento y rechazo de reversión. Las consultas de verificación posteriores también se ejecutaron en ese MySQL aislado.

Resultado de la corrección del orden: 17 pruebas MySQL correctas, sin omisiones; `makemigrations --check --dry-run` no detectó cambios pendientes. La entrega anterior también ejecutó 97 regresiones con `AUTH_TEST_SQLITE=1` y `manage.py check`, ambos correctos; no se repitieron esas regresiones para este ajuste de validación y fixtures. Las pruebas SQLite no sustituyen las pruebas MySQL de la migración. El frontend no cambió.

Archivos de implementación: `apps/projects/models.py`, `apps/projects/services/projects.py`, `apps/projects/services/access.py`, `apps/projects/migrations/0007_project_single_area.py` y `apps/projects/migrations/sql/sp_cambiar_estado_actividad.0007.sql`. Pruebas: `apps/projects/tests/test_projects.py`, `apps/projects/tests/test_segmentation.py`, `apps/projects/tests/test_project_single_area_mysql.py` y `config/settings_test_mysql.py`. Documentación y verificación: este documento, `apps/projects/reviews/project_creation_contract.md` y `apps/projects/migrations/sql/verify_project_single_area.0007.sql`.
