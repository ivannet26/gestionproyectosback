# Gestor de estados y plantillas — 0010

## Compatibilidad y ámbito

Se evoluciona `ProjectTaskStatus`: conserva la clave `(project_id, code)`, nombres y posiciones; añade categoría y color. No se crean entidades de carpeta/lista. Las plantillas pertenecen exclusivamente al proyecto; un administrador de otro proyecto no puede reutilizar el ID para sobrescribirlas. No existe un ámbito organizacional de plantillas en el modelo actual.

`TaskStateDefinition` aporta propiedad y categoría únicamente a los códigos nuevos del catálogo `TaskState`; no sustituye `Task.state_code` ni crea una segunda columna de estado. Los códigos existentes no cambian al editar nombre, color u orden. Los códigos nuevos se generan en servidor. El catálogo público excluye todos los códigos particulares, incluidos los históricos de otros proyectos. Se retienen códigos retirados para no destruir referencias históricas.

Las cuatro categorías son explícitas. Los estados heredados conservan la clasificación de sus códigos funcionales y sus colores anteriores; para códigos no especiales se utiliza el indicador `terminal` existente, nunca el nombre. Scrum «COMPLETADO» pertenece a Activo: progreso, vencimiento y posibilidad de subtareas no lo consideran finalizado. Se conserva la excepción histórica de `CANCELADA` en la agrupación por fecha límite.

Las transiciones entre códigos heredados mantienen exactamente `TaskTransition`. Cuando interviene un estado nuevo se permiten cambios dentro del flujo configurado, con las comprobaciones existentes de proyecto, usuario, asignación, áreas, supervisión, motivo, dependencias, ancestros, subtareas y entregables. Completado y Cerrado usan las protecciones de finalización; No iniciado las de pendiente; Activo las de trabajo en curso. Se heredan además los requisitos de motivo y supervisión del par funcional existente. Finalizar o reabrir exige supervisión; reabrir exige motivo. Un nombre como BLOQUEADO no introduce reglas por coincidencia de texto.

El borrador de plantilla puede estar vacío. El flujo aplicado requiere No iniciado, Activo y Cerrado, y admite Completado vacío. Las plantillas iniciales no son registros editables: sus cambios se guardan como copias particulares. Guardar una plantilla no aplica el flujo. Actualizar una plantilla exige revisión coincidente y su ID dentro del proyecto; aplicar el flujo usa su propia revisión independiente.

## Atomicidad y SQL

La aplicación bloquea el proyecto, valida revisión, códigos, categorías y destinos y actualiza configuración y reasignaciones en una transacción. Exige destino explícito para todos los códigos usados retirados, incluidas subtareas y tareas archivadas. Las archivadas solo admiten un destino funcionalmente equivalente y no se restauran ni archivan físicamente. Cualquier fallo revierte también los códigos y metadatos recién creados.

`sp_cambiar_estado_actividad` conserva su firma pública y su transacción; llama a `sp_aplicar_estado_actividad`, que contiene las mismas protecciones sin COMMIT ni ROLLBACK propios. El servicio de configuración llama a este núcleo exclusivamente dentro de su transacción para evitar commits parciales. `fn_regla_estado_actividad` resuelve las categorías a reglas técnicas sin mirar nombres. `sp_validar_estructura_actividad` utiliza esa misma resolución para rechazar padres finalizados. Las comprobaciones de entregables solo se validan realmente en MySQL, no en SQLite.

## Migración y despliegue pendiente

Nueva migración: `proyectos.0010_task_status_templates`, dependiente de 0009. Ninguna migración aplicada se modifica. Añade dos columnas y dos tablas gestionadas, sin claves físicas nuevas contra las tablas heredadas con identificadores unsigned.

Antes de ejecutar en un entorno autorizado: respaldo recuperable, revisión del SQL y parada de escrituras de tareas. Requiere `TASK_STATUS_MIGRATION_MAINTENANCE=1`. El preflight exige las definiciones revisadas de 0009 y del validador de estructura y rechaza tablas/rutinas nuevas preexistentes. MySQL no ofrece DDL transaccional: ante una interrupción posterior a crear tablas debe conservarse el esquema parcial y revisarse manualmente; no se adopta ni elimina automáticamente. El respaldo de rutinas conserva la definición anterior y las definiciones instaladas normalizadas por MySQL, incluidos los atributos de retorno de funciones. El rollback rechaza estados o plantillas particulares existentes y rutinas modificadas posteriormente.

La migración se probó exclusivamente en MySQL temporal sintético. Sigue pendiente aplicarla al entorno real mediante el procedimiento autorizado del responsable; esta tarea no accedió a Aiven ni a bases compartidas.

## Verificación reproducible

Desde backend, con Docker Desktop operativo y la virtualenv existente:

```powershell
pwsh -NoProfile -File ./scripts/verify_task_status_mysql.ps1
```

El script genera credenciales solo en memoria, crea un contenedor nuevo MySQL 8.4 publicado en loopback con puerto aleatorio y una base nueva `gm_test_task_status_templates`. Nunca reutiliza instancias/bases. La configuración dedicada rechaza otro host o nombre y los tests rechazan una base no vacía. Al finalizar elimina únicamente el contenedor identificado y etiquetado por esta ejecución, junto con su base sintética; no elimina la imagen descargada. Restaura las variables de entorno anteriores y no imprime las credenciales.

SQLite explícito, pruebas de API y regresiones del proyecto:

```powershell
$env:AUTH_TEST_SQLITE = '1'
./.venv/Scripts/python.exe manage.py check
./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
./.venv/Scripts/python.exe manage.py test apps.projects.tests.test_state_templates apps.projects.tests.test_task_states apps.projects.tests.test_assignees apps.projects.tests.test_projects apps.projects.tests.test_performance apps.projects.tests.test_task_inline apps.projects.tests.test_favorites --noinput
```

Se comprobaron 121 pruebas SQLite y 13 MySQL, por separado. MySQL incluye instalación y restauración de rutinas, protección de rollback con datos, atomicidad del núcleo, cierre con entregables, jerarquía, dependencias, motivos, supervisión y responsables adicionales. Los tests SQLite conservan las regresiones y los límites constantes de consultas de la presentación de tareas; no constituyen validación de procedimientos ni medición de latencia productiva.

Frontend: tipado `npx tsc -b`, ESLint dirigido a los archivos modificados/nuevos, 54 pruebas y `npm run build`. El build mantiene una advertencia de paquete principal mayor de 500 kB; el gestor es un chunk diferido separado. Ruff está configurado en el repositorio pero no instalado en la virtualenv ni en el Python disponible; no se añadió ninguna dependencia para sustituirlo.

Para la comprobación visual sintética, iniciar `npm run preview -- --host 127.0.0.1 --port 4177 --strictPort` desde frontend y, en otra terminal:

```powershell
$env:GM_BROWSER_REPORT_DIR = 'C:/ruta/existente/de/resultados'
node tests/verify-state-browser.mjs
```

Chrome headless comprueba la posición del icono, apertura por teclado, búsqueda, Scrum, creación y reordenación con teclado, diálogo secundario, guardado sin aplicar, creación táctil a 375 px, pie visible sin desbordamiento, cancelación y aplicación explícita preservando búsqueda y estados vacíos sin recargar el proyecto. La API de esta comprobación de navegador es sintética e interceptada; persistencia y SQL se prueban por separado en los tests anteriores. Las capturas se revisaron visualmente; no se afirma haber hecho una auditoría con lector de pantalla ni mediciones de producción.

## Endpoints

- GET/PATCH `/api/projects/{project_id}/task-states/`: categoría, color, revisión y conteos de uso solo para administradores; PATCH admite reasignaciones explícitas.
- GET/POST `/api/projects/{project_id}/state-templates/`: plantillas preestablecidas y particulares; escritura independiente del flujo.
- PUT `/api/projects/{project_id}/state-templates/{template_id}/`: actualización de plantilla particular con revisión.
- Las tareas añaden `state_category` y `state_color`; se conservan los demás campos y los contratos de responsables múltiples.

No se hicieron commits ni push; no se modificó el índice de Git.
