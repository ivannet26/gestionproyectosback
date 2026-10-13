# Diagnóstico de rendimiento de Gestión de Proyectos

Fecha de medición: 11 de octubre de 2026, UTC. Alcance: diagnóstico, sin optimizaciones.

## 1. Resumen ejecutivo

Se confirmó trabajo repetido importante, pero **no se reprodujo ni se explicó completamente la espera de 5–10 segundos del entorno observado por el usuario**. No se conectó a Aiven. Las mediciones siguientes pertenecen exclusivamente a una base MySQL local sintética y al código local actual.

Los tres hallazgos prioritarios son:

1. **N+1 en tareas:** 100 tareas requieren 909 consultas como Administrador y 1.213 como Trabajador. Se repiten rol, membresía, estados, etiquetas, dependencias y transiciones. La respuesta crece de forma lineal en consultas y devuelve todas las tareas visibles.
2. **N+1 en proyectos y autorización:** 120 proyectos requieren 367/611 consultas, respectivamente. El rol global vuelve a consultarse dentro de cada serialización y comprobación de permisos; cada proyecto vuelve a buscar su área. Esta lista se carga también al abrir Inicio y Administración.
3. **Cargas duplicadas en desarrollo y barreras secuenciales en la navegación inicial:** Strict Mode duplica las solicitudes de los efectos de proyectos, tareas y Administración. Además, entrar directamente a un proyecto espera sesión → lista/catálogos → detalle/tareas. Se confirmó esta secuencia en el navegador, también con el build de producción.

Hay otros N+1 confirmados: Administración ejecuta 157 consultas para mostrar 50 cuentas; candidatos a trabajadores ejecuta 66 para devolver 58 candidatos. El logotipo incluido en el bundle pesa 1,42 MB. Estos hallazgos no equivalen a atribuirles una demora de varios segundos en producción.

**Redis no es la primera medida recomendada.** Primero reducir consultas repetidas por solicitud, evitar cargas duplicadas y desacoplar cargas de pantallas. Después medir el entorno desplegado para decidir si queda una necesidad real de caché compartida.

## 2. Condiciones, metodología y alcance real

- Backend: HEAD `42525cd` más los cambios locales preexistentes, incluidos servicios/modelos posteriores a 0007. Frontend: HEAD `e8ce69f`, sin cambios locales al comenzar. Se conservaron los cambios existentes.
- Windows, Ryzen 7 250, 8 núcleos/16 procesadores lógicos, aproximadamente 15,3 GiB de RAM; Python 3.14.4, Django 5.2.17, MySQL 8.0.46, Node 24.21.0, React 19.2.8 y Vite 8.3.0.
- Base exclusiva `gm_perf_diagnostic_20261011`, MySQL en loopback. Tablas creadas directamente mediante `schema_editor` desde los modelos para el fixture; **no se ejecutó ninguna migración**. No existe `proyecto_area` en este fixture. Cada proyecto tiene un `area_id`; el trabajador evaluado tiene dos filas en `trabajador_area`.
- Datos sintéticos: 3 áreas, 2 activas; 60 cuentas; 120 proyectos no archivados, 100 en un área y 20 en otra; 121 tareas repartidas en proyectos con 1, 20 y 100 tareas. El trabajador principal pertenece a ambas áreas y tiene participación activa y permisos de contribución. Todas las tareas medidas están asignadas a él, pendientes y con descripción/una etiqueta. Sin dependencias, árbol profundo, requisitos ni solicitudes de recuperación. Estados estándar, sin configuración personalizada. No es una muestra representativa certificada de producción.
- Se inspeccionaron exclusivamente definiciones estructurales del archivo local `BD/GM_Gestor_Proyectos_MySQL_Estructura_Actualizado_post007.sql`. El nombre anterior sin `_post007` ya no estaba disponible. No se importaron sus registros ni credenciales.
- El fixture conserva los modelos y añade los cinco índices de seguimiento relevantes del SQL de referencia. **No reproduce todo el esquema físico**, sus tipos unsigned, columnas ajenas al ORM, restricciones, índices compuestos, procedimientos ni triggers. Los planes SQL son orientativos para este conjunto; no sustituyen los planes de Aiven.
- Endpoints: Django `Client`, autenticación real de la aplicación con tokens sintéticos, conexión cerrada antes de cada solicitud, seis ejecuciones por combinación. Se separa la primera ejecución de la mediana de las cinco siguientes. No se vació el buffer pool: “primera” no significa disco/base de datos fría.
- SQL: `connection.execute_wrapper` y reloj monotónico alrededor de cada ejecución. Se agrupan sentencias parametrizadas, sin guardar valores sensibles en este informe. El contador incluye instrucciones de inicialización de sesión SQL. El tiempo SQL es tiempo observado por el cliente MySQL; **no es CPU pura del servidor SQL**, ni incluye necesariamente conexión, commit y todo el procesamiento posterior.
- HTTP/navegador: aplicación real, sin mocks de API; Chrome headless a 1440 × 900, sin throttling de red/CPU. Backend mediante WSGI local multihilo de diagnóstico, `DEBUG=True`, `CONN_MAX_AGE=0`, sin TLS. Frontend Vite de desarrollo frente a build de producción servido localmente sin compresión. **No se probó un servidor de aplicación de producción.**
- Tres recorridos por modo y rol. Sesión sintética válida al abrir; autenticación y refresh se ejecutan realmente. Navegación SPA activada mediante historial y evento de navegación, sin recargar; entrada directa mediante navegación del documento. Recarga conserva cachés del navegador; cada recorrido comienza con perfil nuevo.
- “Contenido útil”: indicadores visibles de Inicio; tarjetas reales en Proyectos; las 100 tareas en el proyecto; lista/formulario de cuentas en Administración. Detección DOM más dos frames, con sondeo de 20 ms. Es una aproximación instrumentada, no una evaluación humana ni una métrica LCP certificada. Inicio puede mostrar datos simulados antes de completar su sidebar.
- CPU frontend: métricas CDP `ScriptDuration` y `LayoutDuration`. Incluyen trabajo del navegador y callbacks durante la operación; no son duración exclusiva de React. No se insertó un Profiler en componentes.
- Se descartaron ensayos iniciales de Administración en desarrollo con rechazo transitorio de conexiones del pequeño backlog del servidor de diagnóstico. Se aumentó únicamente el backlog temporal a 128 y se repitió desarrollo completo. Los recorridos finales no presentan fallos HTTP ni excepciones JavaScript detectadas. Esto **no se atribuye al servidor real**.

## 3. Mapa de pantallas, solicitudes y dependencias

Las rutas efectivas están en `frontend/src/routes.ts`; el montaje y transporte, en `src/App.tsx` y `src/features/auth/api.ts`.

| Pantalla/acción | Componentes y hooks principales | HTTP y momento de ejecución |
| --- | --- | --- |
| Restaurar sesión / login | `App.useEffect`, `refreshSession`, `LoginPage`, `login` | En cada carga del documento: `GET /api/auth/csrf/` → `POST /api/auth/refresh/`. Login explícito: CSRF → `POST /api/auth/login/`. No hay `GET me` adicional desde este frontend. |
| Todas las rutas autenticadas / sidebar | `AppShell.useEffect`, `ProjectNavigation`, `getProjects`, `getProjectCatalogs` | Después de sesión: `GET /api/projects/` y `GET /api/projects/catalogs/` en paralelo, unidos por `Promise.all`. También se ejecutan en Inicio y Administración. Se conservan en estado mientras vive `AppShell`; no se repiten por cada enlace. |
| Inicio `/` | `DashboardPage`, `DashboardSection`, `KpiCard`, `mockData.ts` | No solicita indicadores al backend: usa datos simulados locales. Sí comparte la carga global anterior. El botón de crear espera esa carga, los indicadores no. |
| `/proyectos` y `/proyectos/resumen` | `ProjectList`, datos recibidos de `AppShell` | No agrega solicitudes propias. Ambas rutas usan el mismo componente; cards y sidebar reciben la misma lista. |
| `/proyectos/:projectId` / Lista de tareas | `ProjectRoute` → `ProjectWorkspace.useEffect` → `TaskTree` | `ProjectRoute` espera `catalogLoading`, que en realidad también depende de toda la lista de proyectos. Luego `GET /api/projects/{id}/` y `GET /api/projects/{id}/tasks/` en paralelo. Otro `Promise.all` retiene el detalle hasta terminar tareas. Al salir y volver, se remonta y repite ambas solicitudes. |
| Crear/editar tarea y subtarea | `TaskForm`, `TaskProperties`, `ResponsiblePicker`, `LabelEditor` | Al abrir, reutiliza proyecto, participantes, estados y tareas descargadas. Búsqueda de responsable local, sin HTTP por pulsación. Guardar usa POST/PATCH y después `loadTasks()` descarga nuevamente la lista completa. No se midió escritura. |
| Estados de proyecto | `TaskStatusConfiguration.useEffect` | Al abrir: `GET /api/projects/{id}/task-states/`; guardar: PATCH al mismo endpoint, después recarga tareas. El detalle ya trae estados, pero este GET obtiene también revisión vigente: no retirarlo sin conservar concurrencia y autorización. |
| Estado y dependencias de tarea | `TaskStateForm`, `DependencyForm`, `ProjectWorkspace` | Apertura usa datos cargados; POST a `tasks/{taskId}/state/`, POST/DELETE a `tasks/{taskId}/dependencies/`; luego GET completo de tareas. Dependencias y transiciones ya viajan en cada tarea. |
| Crear proyecto, dos pasos | `CreateProjectModal`, `ProjectConfiguration`, `getWorkerCandidates` | Catálogos reutilizados. En paso 2/modalidad asignados: `GET /api/projects/workers/?area_ids={id}&q=...`; búsqueda aplicada mediante `searchTerm`, no solicitud por cada carácter escrito. Crear: POST `/api/projects/`, incorpora respuesta local y navega al proyecto. |
| `/administracion/cuentas` | `AdminAccountsPage.useEffect` y `load` | Tres GET en paralelo: `/api/auth/admin/accounts/`, `/api/auth/admin/recovery-requests/`, `/api/auth/admin/areas/`. Todo el contenido espera a los tres. Al remontar se repiten; operaciones de invitación/recuperación vuelven a cargar el conjunto. Comparte además sidebar/catálogos. |
| Fases, seguimiento, entregables, auditoría y otros enlaces | Enrutamiento actual y archivos de dominio | No hay pantallas independientes implementadas/enrutadas para ellos en el frontend inspeccionado. `apps/activities/urls.py` y `apps/tracking/urls.py` están vacíos; no se incluyen en `config/urls.py`. `phase_id` existe en tareas, pero no se pide una colección de fases al abrir estas pantallas. No se inventaron mediciones para rutas inexistentes. |

`config/urls.py` también publica organización y trabajadores (`/api/organization/areas/`, `/api/organization/specialties/`, `/api/workers/`). No hay llamadas de las pantallas anteriores a estos ViewSets. Se inspeccionaron permisos, serializers y consultas: requieren Administrador; trabajadores usa `select_related("area")` y `prefetch_related("worker_specialties__specialty")`. No se midieron sus listas, ni G. Equipos, que no constituye una pantalla funcional equivalente en estas rutas.

### Autenticación y secuencias

`refreshSession` comparte la promesa `renewal`: se observó **un** CSRF y **un** refresh inicial incluso bajo Strict Mode. `apiRequest` reintenta una vez tras 401, esperando CSRF → refresh → solicitud original. En los recorridos con sesión válida no hubo 401 ni renovaciones intermedias. Queda pendiente medir expiración concurrente, revocación y fallos de refresh; no hay evidencia de un bucle de renovación que explique los 5–10 s.

Ejemplo medido, entrada directa al proyecto de 100 tareas, producción/Administrador; tiempos desde el primer recurso del documento:

| Solicitud | Inicio, ms | Duración HTTP, ms |
| --- | ---: | ---: |
| CSRF | 36,87 | 2,49 |
| Refresh | 40,09 | 12,27 |
| Proyectos | 65,61 | 111,63 |
| Catálogos | 65,79 | 11,27 |
| Detalle | 189,48 | 16,87 |
| Tareas | 189,66 | 311,78 |

La lista de proyectos termina antes de que empiece tareas, aunque el proyecto ya está identificado en la URL. La espera serial está confirmada; el ahorro exacto de desacoplarla debe medirse tras una eventual modificación.

## 4. Mediciones por pantalla

Milisegundos, medianas de tres recorridos. A = Administrador; T = Trabajador. “Directa” recarga documento con sesión válida; “SPA” entra desde otra pantalla ya autenticada; “regreso” vuelve después de salir. Inicio directo es el primer documento/perfil nuevo; los demás directos son recargas dentro del recorrido, no caché de recursos completamente fría.

| Pantalla/rol | Producción directa | Producción SPA | Producción regreso | Desarrollo directa | Desarrollo SPA | Desarrollo regreso |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Inicio A | 131,95 | — | 15,73 | 336,37 | — | 39,92 |
| Inicio T | 128,91 | — | 20,25 | 255,75 | — | 73,73 |
| Proyectos A | 207,42 | 45,29 | 25,19 | 402,64 | 78,49 | 61,08 |
| Proyectos T | 299,60 | 46,35 | 24,27 | 596,99 | 87,43 | 87,68 |
| Proyecto/tareas A | 544,20 | 342,14 | 547,97 | 1.089,00 | 712,20 | 688,72 |
| Proyecto/tareas T | 826,05 | 491,43 | 712,11 | 1.531,50 | 1.049,67 | 967,44 |
| Administración A | 158,73 | 115,33 | No medido | 224,47 | 151,50 | No medido |

Los retornos a tareas no mejoran de forma consistente: vuelven a hacer todo el trabajo. Tres muestras no permiten un p95 fiable ni concluir que el retorno es intrínsecamente más lento. Intervalos observados en producción para tareas: directa A 530–560 ms, directa T 821–845 ms; regreso A 532–672 ms, T 706–733 ms.

### Cantidad y volumen de solicitudes

Se cuentan solicitudes API, excluyendo OPTIONS. Volumen HTTP aproximado incluye cabeceras recibidas de API; no es solamente JSON. Las solicitudes solapadas no deben sumar sus duraciones para estimar la espera visual.

| Operación | API producción / desarrollo | Volumen API producción / desarrollo | Consultas SQL HTTP producción / desarrollo |
| --- | ---: | ---: | ---: |
| Inicio o Proyectos, carga de documento A | 4 / 6 | 69,3 / 136,3 kB | 395 / 772 |
| Inicio o Proyectos, carga de documento T | 4 / 6 | 69,4 / 136,4 kB | 642 / 1.264 |
| Proyecto/tareas, directa A | 6 / 10 | 152,5 / 302,7 kB | 1.324 / 2.630 |
| Proyecto/tareas, directa T | 6 / 10 | 148,2 / 294,0 kB | 1.881 / 3.742 |
| Proyecto/tareas, SPA A | 2 / 4 | 83,2 / 166,4 kB | 929 / 1.858 |
| Proyecto/tareas, SPA T | 2 / 4 | 78,8 / 157,6 kB | 1.239 / 2.478 |
| Administración, directa A | 7 / 12 | 81,5 / 160,7 kB | 569 / 1.120 |
| Administración, SPA A | 3 / 6 | 12,2 / 24,4 kB | 174 / 348 |
| Regreso a Inicio/Proyectos | 0 / 0 | 0 / 0 | 0 / 0 |

Hay preflight CORS por `Content-Type: application/json` y/o Authorization entre orígenes distintos. Primera apertura de Inicio: 3 OPTIONS en producción y normalmente 5 en desarrollo; primera navegación a tareas: 2 y 4. Luego el navegador reutiliza preflights durante su vigencia. Su coste local fue pequeño; falta medirlo en la red desplegada. `Cache-Control: no-store` en API es explícito, no un fallo de caché que deba retirarse sin diseño de seguridad.

### HTTP, backend y SQL por endpoint

Medianas tomadas de los recorridos del navegador con build de producción. Backend = tiempo hasta construir respuesta WSGI mediante instrumentación temporal `Server-Timing`. SQL = suma de ejecución observada por el driver. Bytes HTTP incluyen cabeceras. El resto no debe llamarse automáticamente “red Aiven” o “serialización”: contiene varias etapas y concurrencia local.

| Endpoint / rol | HTTP ms | Backend ms | SQL ms | Consultas | Bytes HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| CSRF A | 3,06 | 0,55 | 0 | 0 | 841 |
| Refresh A | 12,27 | 9,96 | 3,09 | 18 | 1.475 |
| Refresh T | 13,73 | 11,74 | 3,66 | 20 | 1.527 |
| Proyectos A | 139,59 | 133,76 | 59,34 | 368 | 65.825 |
| Proyectos T | 233,35 | 228,36 | 92,83 | 612 | 65.945 |
| Catálogos A | 15,10 | 7,93 | 4,39 | 9 | 1.165 |
| Catálogos T | 13,51 | 8,77 | 4,58 | 10 | 1.093 |
| Detalle A | 19,43 | 15,41 | 6,47 | 19 | 1.992 |
| Detalle T | 25,61 | 22,28 | 10,77 | 25 | 1.995 |
| 100 tareas A | 311,78 | 307,54 | 131,78 | 910 | 81.198 |
| 100 tareas T | 490,20 | 485,40 | 200,52 | 1.214 | 76.799 |
| Cuentas A | 78,12 | 72,39 | 38,40 | 158 | 10.840 |
| Recuperaciones A, vacío | 17,87 | 11,90 | 6,10 | 8 | 640 |
| Áreas Administración A | 21,93 | 13,89 | 7,61 | 8 | 714 |

Las medianas son marginales por columna, no necesariamente pertenecen a una misma petición. Se reúnen 6–12 observaciones por endpoint/rol según el recorrido. El servidor HTTP incluye una instrucción de inicialización adicional respecto al `Client`; no mezclar sus contadores como si fueran discrepancias del código funcional.

### Endpoints aislados: primera solicitud y repeticiones

`Client` sin transporte HTTP: primera / mediana de cinco siguientes; bytes de cuerpo JSON sin cabeceras. Las consultas se mantuvieron constantes en estas seis ejecuciones.

| Endpoint / rol / volumen | Primera ms | Mediana ms | SQL mediano ms | Consultas | JSON bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Proyectos A, 120 | 102,21 | 105,13 | 44,27 | 367 | 65.173 |
| Proyectos T, 120 | 206,30 | 196,13 | 78,16 | 611 | 65.293 |
| Tareas A, 1 | 11,76 | 8,65 | 3,05 | 18 | 804 |
| Tareas A, 20 | 60,67 | 61,83 | 25,34 | 189 | 16.085 |
| Tareas A, 100 | 277,59 | 276,11 | 115,13 | 909 | 80.545 |
| Tareas T, 1 | 12,33 | 12,03 | 3,77 | 25 | 760 |
| Tareas T, 20 | 90,06 | 88,17 | 33,63 | 253 | 15.205 |
| Tareas T, 100 | 410,36 | 440,86 | 174,54 | 1.213 | 76.145 |
| Estados A | 6,34 | 4,87 | 1,37 | 11 | 716 |
| Estados T | 9,50 | 9,08 | 2,54 | 15 | 717 |
| Candidatos A, 58 | 37,39 | 32,38 | 11,60 | 66 | 3.582 |
| Cuentas A, 50 | 51,14 | 52,38 | 19,44 | 157 | 10.195 |
| Perfil `me` A | 94,67 | 5,37 | 1,64 | 11 | 249 |
| Perfil `me` T | 5,94 | 6,55 | 2,18 | 13 | 288 |

La primera petición `me` fue también la primera del proceso de diagnóstico, por lo que incluye calentamiento/importaciones. No se atribuyen sus 94,67 ms a la base de datos.

Login explícito se probó aparte tres veces por rol, con CSRF y contraseña sintética: mediana A 286,98 ms, T 286,10 ms; SQL mediano 2,90/3,34 ms. Refresh posterior: 7,03/7,92 ms y 17/19 consultas. Login incluye comprobación de contraseña y operaciones transaccionales; no se perfiló su CPU por función. No explica una espera reiterada de 5–10 s en cada navegación SPA.

### Trabajo del frontend

| Operación | Script / layout producción, ms | Script / layout desarrollo, ms |
| --- | ---: | ---: |
| Inicio A, documento nuevo | 41,73 / 42,52 | 124,98 / 46,50 |
| Proyectos A, SPA | 9,93 / 5,12 | 53,63 / 5,13 |
| Tareas A, SPA, 100 | 10,85 / 17,15 | 75,27 / 16,21 |
| Tareas T, SPA, 100 | 10,79 / 17,39 | 87,99 / 30,45 |
| Administración A, SPA | 8,31 / 4,70 | 55,15 / 5,06 |

La producción generó JS principal de 352,57 kB (106,54 kB estimados gzip), CSS de 55,14 kB (10,11 kB gzip), y PNG de logotipo de 1.418,27 kB. El servidor temporal no aplicó gzip. La primera carga transfirió aproximadamente 1,95 MB en producción y 7,67 MB en desarrollo, incluidos API y recursos. La diferencia no puede asignarse exclusivamente a Strict Mode: desarrollo también sirve módulos, cliente HMR y dependencias sin el empaquetado de producción.

## 5. Causas comprobadas y localización

### A. N+1 en serialización de tareas

`apps/projects/views.py:92`, `TaskListView.get`, llama `task_snapshot` por tarea. En `apps/projects/services/presentation.py:7` se realizan consultas dentro de ese bucle, aunque varias dependen solamente del usuario/proyecto.

En una respuesta Administrador de 100 tareas, la traza agrupada contiene:

- 304 consultas a `usuario_rol` (incluidas comprobaciones comunes de acceso).
- 100 comprobaciones de membresía, incluso para Administrador.
- 100 lecturas de `proyecto_estado_actividad` y, al estar vacío, 100 lecturas del catálogo global.
- 100 lecturas de etiquetas, 100 de dependencias y 100 de transiciones.

El responsable ya usa `select_related("responsible")`: ese vínculo no es el N+1 observado. `configured_states` (`services/statuses.py:24`), `can_create_tasks` (`services/access.py:85`) y `has_supervision` añaden trabajo repetido. Con este fixture, los conteos medidos siguen exactamente `9 + 9N` para A y `13 + 12N` para T. **No son fórmulas universales**: cambian con permisos, estados configurados y ramas de autorización.

El problema comprobado es la cantidad de viajes SQL y trabajo ORM. Todavía falta medir qué proporción de la demora real corresponde al RTT de cada viaje hacia Aiven.

### B. N+1 en proyectos, rol y área

`ProjectListView.get` (`views.py:68`) serializa hasta 200 proyectos sin paginación navegable. `project_snapshot` (`services/projects.py:29`) consulta el área y el rol por proyecto; `User.global_role` (`apps/authentication/models.py:45`) ejecuta SQL en cada acceso, sin reutilización dentro de la petición.

En 120 proyectos A se observaron 243 consultas iguales de rol y 120 consultas de área: 363 de las 367 instrucciones. Para T se agregan comprobaciones de rol y participación; total 611. La consulta principal no lee `proyecto_area`, sino `proyecto.area_id`. La pertenencia múltiple del trabajador sigue resolviéndose mediante `trabajador_area`.

La respuesta incluye descripción, fechas y permisos aunque `ProjectList` renderiza principalmente nombre, área y modalidad. En el fixture devuelve 65 kB; el sidebar también recibe esa lista completa. El potencial de ahorro está confirmado por contenido/consumo del contrato, pero no se simuló un endpoint reducido ni se midió su ahorro final.

### C. Efectos duplicados y bloqueo de cargas

`frontend/src/main.tsx:11` activa Strict Mode. Los efectos de `AppShell:37`, `ProjectWorkspace:37` y `AdminAccountsPage:46` hacen solicitudes sin deduplicación compartida de datos. Las banderas `current` evitan aplicar respuestas obsoletas, pero no evitan que la petición ya iniciada llegue al servidor.

La captura HTTP muestra dos listas/dos catálogos en desarrollo frente a una de cada en producción; cuatro GET al entrar a tareas frente a dos; seis GET propios de Administración frente a tres. Esto confirma el efecto real en este frontend, no una atribución general a React. No se recomienda quitar Strict Mode como optimización de producción.

Además, `ProjectRoute:20` espera la carga conjunta de lista y catálogos; `ProjectWorkspace:39` espera detalle y tareas conjuntamente. La cascada de la sección 3 muestra el bloqueo. Al regresar a Inicio/Proyectos se observaron cero solicitudes, por lo que **no es correcto afirmar que toda navegación recarga todo**.

### D. Administración y candidatos

`AdminAccountsView.get` (`apps/authentication/views.py:239`) usa `select_related("worker", "invitation")`, pero consulta rol y `area_summary` por cuenta. En 50 cuentas: 53 consultas a roles, 50 `EXISTS trabajador_area`, 50 consultas de áreas, más consultas comunes; total 157. Recuperaciones sí usa `select_related` y no mostró este patrón con el conjunto vacío.

`worker_candidates` (`services/projects.py:105`) hace un `COUNT(DISTINCT proyecto_id)` por candidato: 58 conteos para 58 resultados. `eligible_workers` usa agregados/Exists en la selección inicial, pero no agrega ese contador de proyectos. El límite 100 no es paginación. Administración limita cuentas/recuperaciones a 50 sin siguiente página; la API no configura una paginación global en DRF.

### E. Volumen y carga inicial de recursos

El PNG del sidebar de 1,42 MB es un coste de transferencia confirmado por el build; la primera carga real del navegador local supera 1,9 MB. No se demostró que sea el cuello de botella en la conexión del usuario. No hay separación lazy de páginas en `routes.ts`; todos los componentes se importan estáticamente. Debe evaluarse después de los N+1, especialmente para primera visita/red lenta.

## 6. SQL, índices y EXPLAIN

Se ejecutó `EXPLAIN FORMAT=JSON` únicamente sobre SELECT capturados de proyectos, detalle y tareas de Trabajador. No se ejecutó EXPLAIN contra Aiven ni se cambiaron índices del repositorio.

- El SQL de referencia ya contiene `ix_proyecto_seguimiento(area_id, archivado, estado_codigo, fecha_fin)`, `ix_actividad_seguimiento(proyecto_id, archivada, estado_codigo, fecha_fin)`, `ix_actividad_persona(responsable_id, archivada, estado_codigo, fecha_fin)`, `ix_miembro_persona(trabajador_id, activo, proyecto_id)` e `ix_trabajador_area_activo(area_id, activo, apellidos)`. Se reprodujeron esos cinco índices solo en el fixture.
- Listado de proyectos T: plan local con `ALL` sobre 120 proyectos, tabla temporal/filesort y subconsultas de membresía con `eq_ref` usando la PK compuesta. Con tablas tan pequeñas esto **no demuestra un índice ausente ni una consulta principal costosa en producción**.
- Comprobaciones repetidas de membresía: acceso `const` por PK, una fila estimada. Su repetición, no un scan completo por cada tarea, es el problema confirmado.
- Detalle: búsqueda del proyecto por PK; la elegibilidad de participantes incluye agrupación y subconsultas, con temporal/filesort en este plan. Se midieron 10–14 ms por detalle aislado; no se confirmó como cuello dominante.
- Tareas T: el plan eligió recorrido de PK de actividad y responsable `const`; las estimaciones del fixture recién poblado son pequeñas y no equivalen a filas reales ni tiempo de ejecución. No se usó `EXPLAIN ANALYZE` ni se certificó estadística representativa.
- `select_related` de responsable y cuenta/trabajador evita algunas consultas, pero no cubre consultas explícitas por fila. No se recomienda añadir índices indiscriminadamente para intentar arreglar cientos de consultas pequeñas.
- `CONN_MAX_AGE=0` en `config/settings.py:80` implica reconexiones entre solicitudes. En local se cerró la conexión explícitamente al medir endpoints. Falta separar conexión TCP/TLS, RTT y ejecución en el despliegue real antes de recomendar conexiones persistentes/pool.

## 7. Hipótesis pendientes: no tratarlas como causas demostradas

| Hipótesis | Qué falta para confirmarla |
| --- | --- |
| RTT/TLS hacia Aiven amplifica las consultas repetidas hasta varios segundos | Trazas del backend desplegado con conexión, SQL y duración total correlacionadas con un HAR sanitizado. No se midió Aiven. |
| Saturación, bloqueos o recursos limitados del servidor/base compartida | CPU, memoria, conexiones activas, colas, locks y percentiles durante el incidente. No hay métricas operativas de ese entorno. |
| Refresh al expirar añade esperas repetidas o contención | Recorrido controlado con expiración/401 concurrente y rotación; las sesiones válidas medidas no lo mostraron. |
| Árbol de tareas grande/profundo domina el render | `TaskTree.tsx:31` filtra toda la colección por cada nodo; coste potencial cuadrático y descendientes montados incluso al ocultarlos. Faltan árboles grandes/profundos y perfil React. Con 100 tareas planas el script/layout de producción fue pequeño frente al backend. |
| Respuestas grandes dominan la red | Distribución real de número de tareas, longitud de descripciones, etiquetas, transiciones y participantes; medidas con latencia/ancho de banda reales. No hay paginación de tareas. |
| Logo, bundle y compresión explican la espera | Confirmar transferencia, caché y compresión del hosting real. El servidor temporal sin gzip no representa necesariamente ese hosting. |
| Joins/índices de visibilidad son la causa principal | Planes y cardinalidades representativas. Los EXPLAIN del fixture no bastan para recomendar un índice nuevo. |

No se añadió latencia artificial a SQL ni se multiplicó un RTT supuesto para presentar una “demostración” de los 5–10 segundos.

## 8. Concurrencia y 50 usuarios

**No se ejecutó una prueba de carga de 10, 25 o 50 usuarios.** Existe MySQL aislado, pero no datos representativos, distribución real de roles/acciones, servidor de aplicación de producción, infraestructura equivalente ni objetivos de servicio acordados. Las solicitudes simultáneas del navegador no son una prueba de capacidad multiusuario.

El riesgo verificable es trabajo lineal por entidad y solicitudes duplicadas en desarrollo. Aumentar usuarios puede elevar consultas, ocupación de conexiones y colas; no se puede convertir el tiempo de un usuario en la capacidad para 50, ni multiplicar directamente los 5–10 s actuales.

Plan de validación posterior, exclusivamente en réplica aislada:

1. Reproducir infraestructura y esquema post-0007, índices y estadísticas; cargar datos sintéticos con distribuciones aprobadas de proyectos/tareas/subtareas/etiquetas/áreas y permisos, sin extraer datos sensibles.
2. Usar build de producción y el servidor de aplicación previsto. Sesiones de usuarios distintos con mezcla de roles y tiempos de lectura; separar navegación con sesión vigente de login/refresh.
3. Escalones 10, 25 y 50 usuarios: calentamiento y al menos 5 minutos estables por escalón, repetidos tres veces; detener ante saturación/errores sostenidos. No apuntar a Aiven.
4. Registrar p50/p95/p99, rendimiento, errores, CPU/memoria, pool/conexiones y locks; consultas por operación, bytes y contenido útil. Verificar permisos en las respuestas bajo concurrencia.

## 9. Recomendaciones priorizadas y criterios de aceptación

Son propuestas: **ninguna se implementó**. Esfuerzo orientativo de desarrollo y pruebas, no compromiso de plazo. Los umbrales son objetivos a validar, no resultados ya alcanzados.

| Orden | Cambio propuesto | Esfuerzo | Riesgo permisos/datos | Criterio medible posterior |
| --- | --- | --- | --- | --- |
| 1 | Resolver rol/contexto de autorización una vez por petición; cargar estados y membresía por proyecto; agrupar etiquetas, dependencias y transiciones de tareas | 2–4 días | Alto si se omiten filtros del Trabajador o supervisión. Reutilización solo dentro de la petición inicialmente | Pasar de 909/1.213 a ≤25 consultas para 100 tareas en este fixture; pendiente casi constante entre 1/20/100. Igualdad de datos/permisos y pruebas de revocación. |
| 2 | Serializar proyectos sin consulta de área/rol por fila; anotar membresía/autorización efectiva manteniendo `area_id` | 1–2 días | Alto: área activa, confidencialidad, baja de membresía y roles deben conservarse | ≤15 consultas para 120 proyectos, sin crecimiento por fila; mismos IDs autorizados y permisos. |
| 3 | Desacoplar lista global/catálogos de detalle/tareas; deduplicar cargas en curso y evitar trabajo obsoleto | 1–2 días | Medio: estado frontend por usuario/sesión, nunca reutilizable tras logout/cambio de permisos | Una solicitud de cada recurso aun con Strict Mode; GET del proyecto no espera GET de la lista. Medir reducción de tiempo útil directo sin ocultar errores. |
| 4 | Agrupar roles/áreas en cuentas y conteos de proyectos en candidatos | 1–2 días | Alto: no convertir pertenencia múltiple de trabajadores en área única ni ampliar candidatos | Cuentas 50 y candidatos 100 con ≤12 consultas cada uno, incluyendo auth. Mismos resultados y acceso Trabajador denegado. |
| 5 | Definir paginación y proyección mínima por pantalla; estrategia de tareas jerárquicas y refresco tras mutación | 3–5 días | Alto: no paginar antes de filtrar autorización ni exponer padres/dependencias ocultos | Página limitada y navegable; tamaño máximo de respuesta acordado; sin límites silenciosos de 200/50/100; recarga tras una edición no descarga todo cuando no es necesario. |
| 6 | Reducir peso del logo y verificar compresión/caché de estáticos; estudiar partición de código | 0,5–1,5 días | Bajo, solo recursos públicos | Logo apropiado al tamaño de presentación, objetivo ≤100 kB; primera transferencia de estáticos ≤500 kB según formato/caché acordados. API sensible sigue sin caché pública. |
| 7 | Medir luego conexión/TLS, pool e índices con datos representativos; perfilar árbol si crece | 1–3 días de investigación | Medio/alto en base y consistencia | Conexión/SQL/render separados en trazas; justificar cada índice/pool con mejora de p95 y límites de conexiones. Árbol grande sin bloqueos de hilo >50 ms repetidos. |

Tras los primeros cambios, repetir exactamente el fixture y recorridos de este informe. Objetivo provisional local: backend de 100 tareas <150 ms y pantalla directa <500 ms en producción de frontend, además de reducción de consultas. Para el despliegue y 50 usuarios, acordar SLO antes de ensayar; por ejemplo, p95 de contenido útil <2 s y errores <1%, **aún no demostrado**.

## 10. Seguridad y caché / decisión sobre Redis

Se comprobaron lecturas autenticadas con tres perfiles sintéticos:

- Administrador: 120 proyectos, 100 tareas del proyecto medido y acceso a cuentas.
- Trabajador de dos áreas, miembro y responsable: 120 proyectos, sus 100 tareas; Administración y candidatos administrativos responden 403.
- Trabajador de otra área respecto al proyecto medido: solo 20 proyectos; detalle/tareas del proyecto ajeno responden 404; Administración 403.

Esto no reemplaza una suite completa de permisos. Las mejoras deberán conservar áreas activas, pertenencia múltiple de trabajadores, confidencialidad, disponibilidad, membresías revocadas, tarea asignada, rol de proyecto/supervisión, estado terminal y flags efectivos. `proyecto.area_id` debe seguir siendo la única área del proyecto; no reintroducir `proyecto_area` como optimización.

Redis no elimina el N+1 de una primera petición o un cache miss, ni la secuencia de carga ni el bundle pesado. La primera opción es contexto por petición y consultas agrupadas. No se justifica incorporarlo con la evidencia disponible.

Después, podría evaluarse caché de catálogos realmente compartidos/versionados o infraestructura de limitación distribuida si un despliegue multinodo lo requiere. Las listas, permisos y tareas son sensibles: una caché futura necesitaría claves segregadas por identidad/alcance, revisión de autorización vigente, invalidación por cambios de rol, áreas activas, membresía, flags, estado de proyecto, asignación, configuración de estados y contenido; purga al cerrar sesión y prohibición de servir resultados de otro usuario. TTL solo no garantiza revocación inmediata. No cachear tokens/respuestas de login/refresh para acelerar pantallas ni quitar la comprobación de revocación de `AuthToken` sin un diseño específico auditado.

## 11. Ejecución, límites y cierre

Comandos y verificaciones ejecutados:

- `git status --short`, `git diff --stat`, `git diff --check` y lecturas de instrucciones/código en ambos repositorios. Se capturaron hashes del contenido backend preexistente para verificar preservación.
- Inicio de MySQL con `--no-defaults`, `--bind-address=127.0.0.1`, puerto aislado y datadir temporal previamente dedicado a pruebas. Creación de una base nueva exclusiva; sin migraciones ni reutilización de datos compartidos.
- Scripts temporales externos al repositorio: creación de fixture, 144 peticiones medidas de endpoints (12 endpoints × 2 roles × 6 repeticiones), captura de SQL, EXPLAIN seleccionados y servidor instrumentado. Las denegaciones esperadas del Trabajador forman parte de esas 144, no son fallos de rendimiento.
- `npm.cmd run build -- --outDir <directorio-temporal>/dist`, con `VITE_API_BASE_URL` apuntando solo a loopback: correcto, 161 módulos. Advertencia esperada por salida externa, sin vaciar directorios existentes.
- `npm.cmd run dev -- --host 127.0.0.1 --port 4189 --strictPort` y Chrome/CDP: 12 recorridos finales, 3 por combinación de modo/rol, 108 observaciones de pantalla. Sin errores HTTP/JS en esos recorridos finales. Se conservaron aquí agregados y evidencia, no tokens ni cuerpos de sesión.
- 6 logins + 6 refresh locales con CSRF; correctos. 12 lecturas adicionales para contrastar visibilidad/autorización; resultados indicados en sección 10.
- `python manage.py check --settings=perf_settings`, configuración temporal MySQL aislada: sin incidencias. No se ejecutaron `migrate`, `--fake`, pruebas contra Aiven ni push. No se ejecutó lint porque no se cambió código frontend; el build se usó para la comparación solicitada.

El único entregable permanente de esta auditoría es este Markdown. La instrumentación no se añadió al código de la aplicación; se retiraron los procesos, la base sintética exclusiva y los archivos temporales del diagnóstico. Se preservaron los cambios locales anteriores.

Pendientes esenciales: HAR sanitizado del incidente real; temporización del backend desplegado y conexión/SQL hacia Aiven; métricas de host/base; login/refresh con expiración concurrente; perfiles React y árboles grandes; endpoints de organización/trabajadores no consumidos por estas pantallas; esquema físico completo y volúmenes representativos; backend de producción; prueba controlada 10/25/50 usuarios en réplica aislada. **No hay cifra fiable de capacidad para 50 usuarios ni confirmación de que Redis resuelva el problema observado.**
