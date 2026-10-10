# Revisión de descripción y estados de tareas

## Estado

La migración nueva es `proyectos.0006_task_descriptions_and_project_states`. El usuario confirmó que no se ha aplicado a Aiven ni a ningún otro entorno compartido, por lo que se corrige 0006 sin añadir otra migración. También confirmó que en Aiven existe `actividad.descripcion TEXT NULL` y no existe `proyecto_estado_actividad`; esta ejecución no consulta esa base. Depende de `proyectos.0005_project_worker_create`; mantiene la etiqueta histórica `proyectos` aunque el paquete sea `apps.projects`. Las migraciones y SQL anteriores no se modifican.

El grafo y estado se verifican localmente, sin consultar el historial de Aiven. Antes de una aplicación manual, el responsable debe confirmar que todas las dependencias anteriores están aplicadas y revisar en un MySQL aislado el SQL y la definición real del procedimiento.

## Esquema y SQL previstos

1. Comprobar que `sp_cambiar_estado_actividad` coincide con la versión revisada de `0003` y que no existe `proyecto_estado_actividad`. La columna `actividad.descripcion` puede faltar o existir como una columna ordinaria `TEXT NULL`, sin valor predeterminado distinto de NULL, atributos adicionales ni expresión generada. Se verifica `DATA_TYPE`, `COLUMN_TYPE`, `IS_NULLABLE`, `COLUMN_DEFAULT`, `EXTRA` y `GENERATION_EXPRESSION` mediante metadata; una definición incompatible detiene el proceso antes del DDL. No se leen descripciones durante la instalación.
2. Crear `proyecto_estado_actividad`: clave primaria compuesta `(proyecto_id, estado_codigo)`, nombre de hasta 70 caracteres y posición. Nombre y posición son únicos dentro de cada proyecto.
3. Añadir `actividad.descripcion TEXT NULL` únicamente si falta. Si ya existe y es compatible, no se altera su definición ni sus datos, incluidos charset y collation. Si se crea, las tareas existentes reciben NULL. No se concede ningún permiso nuevo.
4. Ajustar la clave de proyecto a `BIGINT UNSIGNED` y copiar charset/collation del código del catálogo antes de añadir las claves foráneas a `proyecto(id)` y `estado_actividad(codigo)`. Solo se interpolan identificadores de metadata validados.
5. Guardar la definición anterior del procedimiento y `description_created` en el JSON de `MigrationBackup`, sin cambiar el modelo ni su tabla. El indicador comienza en false y pasa a true únicamente después de que termine correctamente el `ADD COLUMN`; una columna preexistente permanece en false. Instalar `sql/sp_cambiar_estado_actividad.0006.sql`: agrega únicamente la comprobación de que el destino está habilitado en el proyecto, después del bloqueo de proyecto/actividad. Conserva firma, transacción propia, permisos, supervisión global del Administrador, validación de entregables, dependencias y jerarquía. El helper SQL histórico no se modifica.

MySQL hace commits implícitos del DDL: la migración tiene `atomic=False`. Una falla parcial exige inspección y recuperación manual antes de reintentar; no deben borrarse tablas, columnas o respaldos para forzar su aplicación. Si falla el `ADD COLUMN`, el respaldo no atribuye la columna a la migración. Si se interrumpe después de crearse pero antes de guardar el indicador, se conserva por precaución y requiere revisión manual. No se ha probado el DDL ni el procedimiento contra un motor MySQL real en esta ejecución.

## Reversión

La reversión exige un indicador de propiedad booleano válido; si falta o es inválido, se detiene antes de cambiar el esquema. Con `description_created=false`, conserva siempre la columna preexistente y sus datos: no consulta su contenido ni ejecuta DDL sobre ella. Con true, exige que la columna siga existiendo con una definición compatible y que no contenga descripciones no vacías antes de permitir su retirada.

En ambos casos exige que no haya configuraciones de estados guardadas y que el procedimiento instalado siga siendo la versión revisada. Si hay datos de estados o diferencias del procedimiento, se detiene sin eliminar esquema. Solo entonces restaura el procedimiento respaldado; retira la columna únicamente si la creó 0006, y posteriormente la tabla nueva mediante la reversión de `CreateModel`. Las comprobaciones y los caminos permitidos están probados con cursores simulados; no se ejecutó una reversión MySQL real.

## Reglas y contrato

- Sin filas propias, el proyecto usa el modelo estándar: PENDIENTE, EN CURSO y CERRADO como nombres explícitos de `PENDIENTE`, `EN_CURSO` y `COMPLETADA`. Conserva los estados auxiliares del catálogo y las transiciones vigentes, incluida la revisión previa al cierre.
- Personalizado permite nombres, orden, incorporación y retirada de códigos ya existentes del catálogo. No crea códigos globales arbitrarios, tipos de tarea ni transiciones nuevas. Se requiere conservar los tres estados principales y una ruta de transiciones hacia el cierre.
- No se retiran estados usados por tareas o subtareas, incluso archivadas. No se reescriben estados almacenados.
- `GET /api/projects/{id}/task-states/` exige acceso al objeto. `PATCH` exige Administrador, proyecto abierto y revisión vigente. El reemplazo de la configuración es atómico.
- El detalle de proyecto añade `task_states`. Las respuestas de tarea añaden `description` y `state_name`; conservan `state_code`. Creación y edición admiten descripción opcional, hasta 10000 caracteres, como texto.
- La edición de descripción es exclusiva del Administrador. El Trabajador conserva sus permisos anteriores; puede incluir descripción al crear una tarea autorizada que queda asignada a él. No se habilitan nuevos campos editables en tareas existentes.
- Responsables: participación activa, cuenta y trabajador elegibles y área autorizada, usando la resolución existente. El Administrador no necesita membresía para gestionar ni supervisar globalmente.
- `RESPONSABLE`, `REVISOR` y `COLABORADOR` siguen siendo conceptos de membresía de proyecto, no roles globales. Los únicos globales son ADMINISTRADOR y TRABAJADOR.
- Si falta la tabla nueva, la creación de proyectos falla antes de escribir registros. Los endpoints devuelven el error controlado del servicio hasta preparar el esquema.

## Archivos de implementación

Backend:

- `apps/projects/models.py`, `serializers.py`, `views.py`, `urls.py`.
- `apps/projects/services/projects.py`, `tasks.py`, `presentation.py`, `statuses.py`.
- `apps/projects/tests/test_projects.py`, `test_task_states.py`.
- La migración 0006, su archivo SQL nuevo y este documento.
- `requirements.txt`: codificación UTF-8 y declaración `drf-spectacular==0.30.0`, versión ya instalada; los demás requisitos no se actualizan.

Frontend:

- `src/routes.ts`, `src/features/dashboard/mockData.ts`.
- `src/features/layout/AppShell/AppShell.tsx`, `Sidebar/Sidebar.tsx`, `NavSection/NavSection.tsx` y su CSS Module.
- En `src/features/projects/`: `ProjectNavigation/` y `TaskStatusConfiguration/` (TSX y CSS Modules nuevos), `ProjectRoute/ProjectRoute.tsx`, `ProjectWorkspace/ProjectWorkspace.tsx`.
- `TaskForm/TaskForm.tsx` y su CSS Module, `TaskStateForm/TaskStateForm.tsx`, `TaskTree/TaskTree.tsx`, `Modal/Modal.tsx`, `services.ts`, `types.ts`.

Los cambios locales previos de ambos `AGENTS.md` se conservan sin edición por esta implementación. Autenticación, archivos de entorno, dependencias de npm y el flujo de creación de proyectos de dos pasos permanecen intactos.

## Verificación y pendientes

Verificación de la implementación anterior: `manage.py check` sin incidencias; `manage.py makemigrations --check --dry-run` sin cambios adicionales; grafo local consistente; 57 pruebas dirigidas aprobadas en el modo ya existente `AUTH_TEST_SQLITE=1` (SQLite en memoria, datos sintéticos); `npm run lint` y `npm run build` aprobados; `git diff --check` sin errores. Se comprobaron 42 hashes de archivos protegidos sin diferencias. Estos resultados de frontend no se volvieron a ejecutar para esta corrección exclusiva de backend.

Corrección de 0006: solo se modifican esta migración, `apps/projects/tests/test_task_states.py` y este documento. Se aprobaron las 15 pruebas de migración y, después, el módulo completo de 29 pruebas de estados y descripción. Cubren columna faltante, definición compatible o incompatible, procedencia del respaldo, fallo de creación, reversión sin pérdida de datos, configuraciones de estados usadas y protección del procedimiento/collation. `manage.py check` no presenta incidencias y `manage.py makemigrations --check --dry-run` no detecta cambios adicionales. Se utiliza exclusivamente el modo aislado existente `AUTH_TEST_SQLITE=1`, con `setup_test_environment(debug=False)`; el SQL MySQL se comprueba con cursores simulados y comparación del procedimiento, no ejecutándolo contra Aiven.

Pendientes manuales: revisar y probar la migración en un MySQL aislado; confirmar dependencias e historial antes de cualquier aplicación autorizada; comprobar teclado, foco y Escape de ambos modales, árbol lateral, creación desde cada proyecto, conservar el borrador al configurar estados, alias/orden, errores de estados usados y flujo de trabajadores. No se abrió el navegador ni se enviaron correos.
