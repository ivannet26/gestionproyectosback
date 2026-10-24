# Revisión 0016: consistencia de cambios de estado

## Motivo y ámbito

El remoto `7d1112520603ad72a399a8bc5fe02181bce8ff12` cambió la política Python y SQL histórico respecto de `c6900c1`. Retiró motivos y responsable activo en archivos usados por las migraciones 0006, 0007, 0009 y 0010; cambió además `0015_task_state_without_assignee.source()` para devolver la fuente anterior sin transformación. Esas ediciones no actualizan procedimientos de una base donde las migraciones ya están registradas.

Las diferencias afectan los SQL `sp_cambiar_estado_actividad` en authentication (before y vigente), los SQL de proyectos before/vigente/0006/0007/0009, `sp_aplicar_estado_actividad.0010.sql` y el Python de 0015. No se volvieron a editar esos archivos aplicados durante esta integración.

0016 alinea los dos helpers instalados: `sp_aplicar_estado_actividad` y `sp_aplicar_estado_actividad_modo`. Después de 0014, el primero era un wrapper que llamaba al segundo. Después de 0016, el primero contiene la política compartida y el segundo delega en él; ambos conservan su firma pública y son seguros para una transacción externa porque no hacen `START TRANSACTION` ni `COMMIT`.

Se conserva la vía ORM vigente de los servicios; no se reinstala una llamada al procedimiento público `sp_cambiar_estado_actividad`, que conserva su contrato histórico transaccional y no debe invocarse dentro de `transaction.atomic()`.

## Reglas conservadas

- Cuenta activa, trabajador activo y un único rol global permitido.
- Proyecto vigente/no archivado y no finalizado ni cancelado; tarea vigente del proyecto.
- Para trabajador: asignación primaria/secundaria, participación activa, área autorizada y permiso de cambio de estado del proyecto.
- Administrador no depende de asignación, responsable de la actividad ni permisos de trabajador del proyecto.
- Destino existente y habilitado en el flujo; códigos particulares de otro proyecto quedan rechazados.
- Bloqueo del proyecto y actividad, auditoría del trigger con autor y operación existentes, no-op sin evento.

No se reinstalan motivos, supervisión de transiciones, responsable activo de la actividad, restricciones de cierre por subtareas, dependencias o revisión de entregables que el remoto ya descartó. El movimiento conserva `parent_id` y atributos ajenos al estado; ORM y SQL conservan ahora también el motivo histórico sin solicitar ni insertar motivos nuevos. El progreso mantiene las reglas vigentes del cambio funcional de estado.

## Preflight, respaldo y operación

- Requiere escrituras de tareas detenidas y `TASK_STATE_POLICY_MAINTENANCE=1`; por defecto el ejemplo de entorno lo deja en 0.
- Dependencia: `proyectos.0015_task_state_without_assignee`.
- Solo acepta el wrapper exacto de 0014 y las variantes revisadas del helper de ese historial: fuente post-7d11125, fuente anterior con motivo y responsable, y fuente de 0015 anterior que ya había retirado el responsable pero conservaba motivo. También reconoce su propia versión para una repetición controlada.
- Una definición desconocida, firma diferente, cambio de seguridad o respaldo incompatible provoca rechazo antes de reemplazar SQL.
- Respaldo: `auth_migration_backup`, clave `task_state_policy_consistency_0016`, con ambas definiciones y sus metadatos originales. Se reutilizan los helpers existentes para preservar definer y sql_mode.
- MySQL DDL no es transaccional. Ante fallo se recrean ambas definiciones anteriores antes de propagar el error; el orden de restauración evita wrappers recursivos intermedios. La reversión exige la misma ventana y rechaza drift posterior.
- No hay cambios de tablas ni datos de tareas por esta migración. El respaldo y el registro de migración son las únicas escrituras de datos de instalación.

No se ejecutó ni se autoriza por esta revisión ningún despliegue sobre Aiven o una base compartida. 0016 queda pendiente de despliegue bajo revisión del operador. Una base que no coincida con los baselines revisados necesita revisión propia; no se usa `--fake` ni se sobreescriben discrepancias.

## Verificación aislada

`scripts/verify_task_status_mysql.ps1 -TestModule apps.projects.tests.test_state_policy_integration_mysql` crea un contenedor MySQL 8.4 nuevo, base sintética exclusiva y puerto loopback dinámico; al terminar elimina contenedor y base.

El fixture existente crea el baseline de esquema sintético anterior a 0010 y aplica las migraciones funcionales reales necesarias hasta 0014. Las dos clases nuevas prueban la instalación actual 0015→0016 y una actualización de la política SQL pre-7d11125: se reconstruyen las definiciones históricas revisadas, se ejecuta la transformación real equivalente de 0015 y luego 0016 mediante `MigrationExecutor`. No se simula la actualización marcándola aplicada sin ejecutarla.

Son 14 casos dirigidos aprobados: manual/move/helpers SQL con estados terminales y vuelta al original, subtareas/atributos/motivo histórico, readonly/revocación, autenticación, destinos no habilitados o foráneos, rollback externo, conflicto 409 sin segunda escritura, no-op, auditoría única, registros de migración, guardas de mantenimiento, fallo DDL con restauración y drift rechazado. Esto verifica el camino de migraciones de Proyectos sobre el baseline sintético existente; no es una instalación de toda la infraestructura ajena al módulo desde cero.

También se ejecutaron 12 pruebas SQLite explícitas de Lista y plantillas, Django `check`, `makemigrations --check --dry-run` y `git diff --check`, sin errores. Las validaciones de procedimientos/triggers y actualización son exclusivamente los casos MySQL anteriores, no SQLite.

Regresiones MySQL adicionales: `test_list_consistency_mysql`, 5 aprobadas; `test_template_application_mysql`, 7 aprobadas. Son 26 pruebas MySQL dirigidas en total, ejecutadas en contenedores temporales separados. `compileall` dirigido es correcto. Ruff está configurado, pero no está instalado en el entorno Python ni hay ejecutable disponible; no se instaló una dependencia adicional para ocultar esa limitación.
