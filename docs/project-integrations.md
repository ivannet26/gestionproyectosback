# Contratos y esquema: integración GM

21/10/2026. Implementación sin commit. No se aplicaron migraciones ni escrituras a Aiven, producción o bases compartidas.

## Contratos añadidos

| Operación | Datos |
| --- | --- |
| GET /api/projects/catalogs/ | specialties [{id,name}] del catálogo real de Organización; task_templates preestablecidas |
| GET /api/projects/teams/?area_id=ID | Equipos activos e integrantes elegibles, solo Administrador |
| POST /api/projects/ | participant_source workers/teams; team_ids; initial_task_states [{name,category,color}] opcionales |
| GET /api/projects/ID/ | team_ids y assignment_teams para Administrador |
| GET /api/projects/ID/assignment-teams/ | Integrantes y elegibilidad efectiva; Trabajador recibe [] |
| POST tareas | start_date opcional; su omisión mantiene el inicio predeterminado existente |
| POST/PATCH tareas | specialty_ids y retained_label_ids, sin mezclar selecciones legadas no vacías |
| POST /api/projects/ID/tasks/TASK/move/ | state_code, before_id (ID o null), expected_revision, reason |
| Snapshots de tareas | manual_position (decimal como texto), move_revision opaca, move_targets prevalidados |
| GET subtareas | Páginas de 30, next_cursor numérico opaco sobre orden manual, ahora por desplazamiento |

Se conserva autenticación/transporte y permisos por objeto. Una posición solo admite anclas del mismo proyecto, estado y padre. null significa al final entre hermanos. La respuesta del movimiento es la lista autorizada confirmada.

La revisión corresponde a tareas del proyecto: cambios concurrentes devuelven 409 y requieren actualización explícita. No se reintenta ciegamente ni se sobrescriben atributos ajenos al movimiento. Los destinos son una prevalidación, no una autorización permanente. Se conserva 409 para conflictos de configuración y fallos de negocio de los procedimientos MySQL; las validaciones de entrada mantienen 400.

## Pertenencia y permisos

Los equipos aportan una instantánea inicial deduplicada de integrantes actuales elegibles según cuenta, trabajador y asociaciones de área vigentes. La creación revalida/bloquea esas entidades y guarda proyecto, participantes, equipos y flujo en una transacción.

ProjectMember permanece como fuente de autorización, con rol COLABORADOR. No se conceden privilegios de responsable/revisor por pertenecer al equipo. Agregar integrantes al equipo después no añade ProjectMember. Revocación de participación y pérdida de elegibilidad siguen siendo efectivas.

El selector de responsables por equipo solo localiza personas ya elegibles y participantes efectivos. No incorpora participantes ni asigna tareas al equipo; reutiliza TaskAssignee y responsable principal.

Se rechazan equipos vacíos, inactivos, de otra área y selecciones ocultas del otro origen. Los proyectos disponibles no reciben asignaciones automáticas. El flujo se mantiene local hasta crear: categorías explícitas, No iniciado/Activo/Cerrado obligatorios y Completado opcional. COMPLETADO de Scrum sigue siendo Activo. Las plantillas preestablecidas no se modifican.

## Migración nueva 0013_project_teams_specialties_order

Dependencias: proyectos.0012_task_detail, organization.0001_initial, teams.0001_initial. No se modificó ninguna migración anterior ni procedimiento.

| Cambio físico | Finalidad |
| --- | --- |
| proyecto_equipo | Asociación múltiple con unicidad proyecto/equipo |
| actividad_orden | Una posición DECIMAL(38,18) por actividad |
| actividad_etiqueta.especialidad_id | Referencia nullable a Especialidad, con índice |
| ck_actividad_etiqueta_clase | Admite specialty y conserva technical/nontechnical |

Los vínculos nuevos siguen el precedente legado db_constraint=False para evitar incompatibilidades de signedness con tablas externas/no administradas. No se afirma que exista una FK física. Los servicios validan integridad y usan transacciones; Django aplica PROTECT a especialidades/equipos referenciados. Sus endpoints devuelven un error comprensible al intentar eliminarlos.

Las etiquetas históricas, requisitos y Activity no se convierten, emparejan por nombres ni eliminan automáticamente. specialty_id identifica las nuevas asociaciones. Para mantener la unicidad legada, su campo físico nombre almacena specialty:<id>; el API y Activity exponen el nombre canónico del catálogo. Renombrar una especialidad mantiene la asociación; Activity guardado anteriormente no se reescribe. Los clientes legados siguen admitidos y no borran asociaciones nuevas al editar etiquetas antiguas.

El backfill copia el equipo legado a ProjectTeam sin modificar Project.team ni participantes históricos. Crea posiciones en incrementos de 1024 sobre el orden anterior determinista; los valores de IDs/fechas no se usan como posiciones. Las tareas nuevas reciben posición al crearse. El relleno diferido contempla filas sin posición introducidas por integraciones legadas.

Un movimiento actualiza normalmente una posición fraccionaria; solo reequilibra hermanos del destino si se agota la precisión. No altera padres, descendientes, responsables, etiquetas, fechas o descripción. Estado/posición/Activity comparten transacción y operation_id. Reutiliza sp_aplicar_estado_actividad interno, sin COMMIT, para conservar atomicidad.

Se ampliaron las fixtures manuales con Specialty, ProjectTeam y TaskOrder. MySQL crea Teams antes de 0013 y limpia los vínculos antes que sus entidades padre.

## Despliegue pendiente de autorización

Estas instrucciones NO se ejecutaron en una base compartida:

1. Revisar respaldo recuperable y correspondencia del esquema real con 0012, incluidas Especialidades y Equipos legados.
2. Detener todas las escrituras de proyectos/tareas y procesos externos. La variable de mantenimiento solo autoriza la migración; no bloquea automáticamente el servidor.
3. Desplegar versiones compatibles y habilitar temporalmente PROJECT_INTEGRATION_MAINTENANCE=1 para la migración. .env.example incluye valor 0; no se modificó .env.
4. Aplicar mediante el proceso autorizado, por ejemplo: python manage.py migrate proyectos 0013_project_teams_specialties_order.
5. Verificar asociaciones/rangos, restituir la variable a 0 y habilitar escrituras con ambas aplicaciones compatibles.

MySQL DDL realiza commits implícitos: atomic=False no ofrece rollback transaccional del esquema. La preparación rechaza tablas de integración preexistentes. Ante fallo parcial, inspeccionar y recuperar; no fingir reversión completa. El rollback automático está bloqueado para evitar perder asociaciones/posiciones y requiere un plan explícito de preservación.

Las pruebas no usan una copia de Aiven. Aplicación de 0013 y comprobación del despliegue real siguen pendientes.

## Evidencias

[Informe, comandos y ocho capturas reales](../../frontend/docs/task-detail-verification/project-integrations/README.md).
