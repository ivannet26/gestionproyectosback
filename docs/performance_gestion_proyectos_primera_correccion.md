# Primera corrección de rendimiento

Fecha: 2026-10-11. Línea base: [diagnóstico previo](performance_gestion_proyectos_diagnostico.md).

## Resultado y alcance

Se reprodujeron los conteos del diagnóstico antes de modificar el código de aplicación, sobre MySQL local aislado. Los cuatro objetivos de consultas se alcanzaron sin paginación, Redis, cambios del contrato ni migraciones nuevas. La lista, detalle y tareas ya no forman una cascada de carga. Administración conserva sus tres solicitudes necesarias, en paralelo; no descarga los catálogos de proyectos si no los necesita.

La mejora es local. No se conectó a Aiven, no se hicieron pruebas de carga ni se verificaron los 5–10 segundos de Proyectos o 3–5 segundos de Administración del entorno compartido. No se afirma que hayan desaparecido.

Los cambios locales anteriores, incluidos la eliminación de ProyectoArea y 0007 con sus SQL, pruebas y documentación, se conservaron. El diagnóstico original no se reescribió. No hubo instalación de dependencias, commit ni push.

## Condiciones de comparación

- MySQL 8.0.46, Python 3.14.4, Django/DRF de la instalación existente; React 19.2.8 y Vite 8.3.0. Windows local, conexiones de aplicación a loopback exclusivamente.
- Misma base sintética antes/después: 120 proyectos, tres áreas (dos activas), 60 cuentas, 58 candidatos elegibles, proyectos representativos con 1, 20 y 100 tareas. Cada tarea tiene responsable y etiqueta; el trabajador medido tiene membresía activa y dos áreas.
- Esquema ORM posterior a 0007, sin proyecto_area, con los cinco índices de seguimiento de proyecto/actividad, responsable, miembro y trabajador_area utilizados en el diagnóstico. No es una copia completa de producción: no se importaron datos reales, todos los triggers ni todos los procedimientos.
- Endpoints: seis ejecuciones por combinación rol/endpoint, cerrando la conexión entre ejecuciones. Se registra la primera y se informa la mediana de las cinco siguientes. Contador y cronómetro mediante execute_wrapper; duración total mediante Django Client. No se mezclan esos tiempos con los HTTP.
- Navegador: Chrome headless, 1440 × 900, tres entradas por pantalla y rol, primero Vite de desarrollo y luego el bundle de producción servido localmente. Backend WSGI multihilo local idéntico en ambos modos, sin servidor/infraestructura de producción. Sin throttling ni concurrencia de usuarios.
- Contenido útil: lista con proyectos, lista de 100 tareas o sección de cuentas poblada, seguida de dos requestAnimationFrame. La entrada directa incluye restauración de sesión; la navegación posterior conserva la sesión y se realiza con los enlaces de React Router.
- CDP registra HTTP y excepciones; instrumentación WSGI temporal añade Server-Timing. Los preflights OPTIONS se excluyen del número de solicitudes de datos indicado abajo. El tamaño se expresa como JSON de respuesta, no como bytes comprimidos de red.
- Los scripts, tokens sintéticos e instrumentación temporal se retiran al finalizar. Las pruebas de regresión permanentes no dependen de ellos.

## Consultas y duración backend

Medianas en milisegundos. A = Administrador; T = Trabajador autorizado. Conteos incluyen autenticación y permisos, no solamente la consulta de negocio.

| Endpoint / fixture | Rol | Consultas antes → después | Backend antes → después | SQL antes → después | JSON bytes |
| --- | --- | --- | --- | --- | --- |
| GET /api/projects/, 120 | A | 367 → 5 | 163,37 → 6,55 | 74,78 → 1,59 | 65.173 |
| GET /api/projects/, 120 | T | 611 → 9 | 232,38 → 10,82 | 96,94 → 3,56 | 65.293 |
| GET /api/projects/3/tasks/, 100 | A | 909 → 11 | 332,69 → 9,60 | 143,78 → 2,96 | 80.545 |
| GET /api/projects/3/tasks/, 100 | T | 1.213 → 15 | 495,76 → 12,87 | 204,30 → 3,66 | 76.145 |
| GET /api/auth/admin/accounts/, 50 | A | 157 → 8 | 60,97 → 7,30 | 24,19 → 1,98 | 10.195 |
| GET /api/projects/workers/, 58 | A | 66 → 7 | 35,52 → 7,78 | 13,09 → 2,56 | 3.582 |
| GET /api/projects/3/ | A | 18 → 13 | 11,60 → 7,85 | 4,11 → 2,17 | 1.350 |
| GET /api/projects/3/ | T | 24 → 17 | 13,72 → 11,78 | 4,29 → 3,10 | 1.352 |
| GET /api/auth/me/ | A | 11 → 6 | 6,05 → 5,41 | 1,77 → 1,31 | 249 |
| GET /api/auth/me/ | T | 13 → 8 | 6,53 → 4,28 | 2,26 → 1,11 | 288 |

El volumen y el contenido JSON no disminuyeron: se compararon exactamente las 33 respuestas completas de los once endpoints medidos para Administrador, Trabajador autorizado y Trabajador sin autorización para el proyecto objetivo. No hubo diferencias, incluidos respuestas 403/404, permisos, estados, participantes y datos de Administración.

La cantidad de tareas no determina la cantidad de consultas:

| Tareas | Administrador antes → después | Trabajador antes → después |
| --- | --- | --- |
| 1 | 18 → 11 | 25 → 15 |
| 20 | 189 → 11 | 253 → 15 |
| 100 | 909 → 11 | 1.213 → 15 |

Las pruebas permanentes comprueban también conteo constante de proyectos con 1/20/120 y de cuentas/candidatos al crecer de 3 a 60 cuentas. Objetivos alcanzados: proyectos ≤15, tareas ≤25, cuentas y candidatos ≤12. El contador WSGI puede incluir una consulta adicional de inicialización de conexión respecto al contador Client; tampoco supera los objetivos.

## Contenido útil y solicitudes por pantalla

Medianas de tres ejecuciones en ms. Solicitudes incluye GET de CSRF y POST de refresh en entrada directa, además de los recursos de pantalla/sidebar. No incluye HTML, assets, WebSocket de Vite ni OPTIONS. Producción significa bundle optimizado, no despliegue real.

| Modo | Pantalla / rol | Entrada directa antes → después | HTTP antes → después | Navegación posterior antes → después | HTTP posterior antes → después |
| --- | --- | --- | --- | --- | --- |
| Desarrollo | Proyectos A | 521,07 → 208,41 | 6 → 3 | No se obtuvo par comparable | 0 en retorno observado después |
| Desarrollo | Proyectos T | 726,82 → 222,53 | 6 → 3 | No se obtuvo par comparable | 0 en retorno observado después |
| Desarrollo | Tareas A | 1.363,24 → 292,70 | 10 → 6 | 939,10 → 108,49 | 4 → 2 |
| Desarrollo | Tareas T | 1.896,48 → 278,14 | 10 → 6 | 1.504,46 → 95,81 | 4 → 2 |
| Desarrollo | Administración A | 305,20 → 241,38 | 12 → 6 | 170,16 → 94,84 | 6 → 3 |
| Producción local | Proyectos A | 271,58 → 125,41 | 4 → 3 | No se obtuvo par comparable | 0 en retorno observado después |
| Producción local | Proyectos T | 401,22 → 126,01 | 4 → 3 | No se obtuvo par comparable | 0 en retorno observado después |
| Producción local | Tareas A | 605,04 → 146,22 | 6 → 6 | 424,77 → 86,86 | 2 → 2 |
| Producción local | Tareas T | 1.138,94 → 172,24 | 6 → 6 | 657,77 → 89,89 | 2 → 2 |
| Producción local | Administración A | 204,23 → 148,00 | 7 → 6 | 163,45 → 60,02 | 3 → 3 |

En Tareas de producción no baja el número de solicitudes: mejora la ejecución SQL y se elimina la espera del detalle/tareas por la lista global. En Administración no se suprimen cuentas, recuperaciones ni áreas, pues las tres alimentan controles existentes. Se elimina la descarga global de catálogos que no utiliza esa pantalla.

Duración HTTP y backend del recurso principal, medianas en ms:

| Modo / recurso / rol | HTTP antes → después | Server-Timing backend antes → después |
| --- | --- | --- |
| Desarrollo / proyectos / A | 224,67 → 12,24 | 146,84 → 8,66 |
| Desarrollo / proyectos / T | 491,62 → 20,35 | 281,14 → 17,25 |
| Desarrollo / tareas / A | 577,37 → 38,35 | 382,24 → 33,19 |
| Desarrollo / tareas / T | 846,75 → 48,02 | 554,38 → 39,24 |
| Desarrollo / cuentas / A | 173,38 → 26,45 | 101,09 → 21,22 |
| Producción local / proyectos / A | 163,20 → 12,62 | 159,30 → 10,00 |
| Producción local / proyectos / T | 286,63 → 21,71 | 284,01 → 16,31 |
| Producción local / tareas / A | 353,49 → 43,40 | 347,18 → 33,26 |
| Producción local / tareas / T | 629,65 → 55,68 | 625,02 → 49,47 |
| Producción local / cuentas / A | 113,01 → 31,19 | 105,54 → 22,88 |

Los GET duplicados de desarrollo compiten entre sí. HTTP incluye espera y transferencia; Server-Timing no incluye toda la vida del transporte. No se interpreta su diferencia como latencia a Aiven.

## Correcciones realizadas

### Backend

- User.global_role aprovecha exclusivamente las relaciones prefetched de la instancia leída para esa solicitud; sin prefetch conserva su consulta original. AccessTokenAuthentication obtiene usuario/trabajador y roles nuevamente en cada solicitud. No hay caché global de autorización.
- project_snapshots une el área única mediante select_related y agrupa las membresías necesarias para permisos de creación. La respuesta sigue exponiendo areas con un único elemento por compatibilidad. No lee ni escribe proyecto_area.
- task_snapshots calcula membresía, supervisión, estados configurados y capacidades una vez; agrupa etiquetas, dependencias y transiciones. Mantiene el filtro de tareas por responsable y el de predecesoras visibles al trabajador, además de las restricciones de proyectos/tareas cerrados y subtareas.
- Administración obtiene roles y resúmenes de áreas por lotes. La existencia de asociaciones de trabajador con áreas inactivas sigue suprimiendo el fallback al área principal; todas_las_areas sigue significando todas las áreas activas.
- Candidatos usa un agregado separado para los conteos de proyectos. No añade un join que multiplique los conteos de roles de eligible_workers ni flexibiliza sus restricciones.
- Login y refresh reutilizan los roles prefetched. consume_stored permite devolver el usuario fresco ya bloqueado por refresh, comprobando que corresponde al token; mantiene bloqueo/consumo/expiración y rotación. Los demás consumidores conservan el comportamiento anterior.

### Frontend y autenticación

- AppShell carga proyectos y catálogos de forma independiente; estos últimos se solicitan solamente para detalle de proyecto o apertura de creación. ProjectRoute monta ProjectWorkspace sin esperar ninguna de esas cargas.
- Una falla del catálogo no oculta detalle/tareas. Los formularios dependientes muestran carga/error y reintento, sin operar con catálogos vacíos. Se reutiliza el diálogo existente.
- apiRequest comparte solamente promesas de GET simultáneos con opciones predeterminadas, por namespace/ruta/retry y época de sesión. Elimina la entrada al resolver o rechazar: no conserva respuestas ni errores después del vuelo, no comparte POST/PATCH/DELETE ni señales de cancelación diferentes.
- Login, logout y limpieza de sesión invalidan los vuelos anteriores. Una renovación tardía no puede reemplazar un login nuevo; el cambio de identidad/rol/áreas/permisos informado por refresh invalida vuelos y remonta el layout autorizado.
- Cada solicitud 401 compara el access usado con el actual: si otra ya lo renovó, reintenta con el nuevo sin iniciar otra rotación. Sigue existiendo una sola promesa de refresh simultáneo y se conserva CSRF.
- Se mantuvo Strict Mode. No se añadieron almacenamientos persistentes de tokens/respuestas ni se alteraron las tres cargas paralelas necesarias de Administración.

Restauración de sesión: ya compartía el refresh bajo Strict Mode; no se eliminó esa validación. En HTTP la renovación pasó de 18 a 12 consultas para Administrador y de 20 a 14 para Trabajador; medianas 15,76 → 14,39 ms y 19,00 → 13,73 ms. Esa parte era pequeña en loopback y no explica por sí sola segundos de espera.

Una prueba determinista del transporte, ejecutada antes de corregirlo, reprodujo dos renovaciones con 401 desfasados. Después requiere una. La prueba de navegador con dos recursos protegidos expirados verificó un POST refresh y dos reintentos 200.

## Seguridad y verificaciones

- Ocho pruebas nuevas en MySQL aislado: conteos constantes; límite de candidatos/cuentas; áreas múltiples/inactivas/todas; autorizaciones frescas; membresías y flags revocados; relaciones/transiciones y estados configurados; expiración, consumo y replay de tokens; CSRF; login y creación con área única y fecha final nula.
- Suite dirigida existente más esas pruebas en SQLite explícitamente aislado: 131 pruebas aprobadas, cero omitidas. Las pruebas SQLite de operaciones con procedimientos usan el aislamiento/mocks propios del proyecto: no sustituyen una validación del procedimiento en MySQL de producción.
- Ocho pruebas frontend del transporte aprobadas, cero omitidas: deduplicación solo simultánea, nuevo GET tras finalizar/fallar, namespaces/métodos/cancelación, limpieza de sesión, refresh fallido, 401 desfasados, renovación tardía y cambio de autorización.
- Chrome: pantallas medidas sin excepciones de JavaScript. Comprobación adicional de producción con la solicitud global de proyectos retenida: se mostró la lista de 100 tareas antes de liberarla. Error sintético de catálogo no ocultó tareas y Reintentar recuperó los controles. Retorno posterior a Proyectos: 9,28 ms / 0 nuevas solicitudes en esa comprobación única, no una mediana comparable antes/después.
- No se realizó una prueba de carga ni una prueba de permisos multiusuario sobre Aiven. Los controles de acceso se comprobaron mediante requests independientes en MySQL y SQLite, no únicamente mediante botones ocultos.
- UI UX Pro Max se utilizó para evitar cascadas de datos independientes. Web Design Guidelines orientó los estados de carga/error/reintento accesibles. No se cambió la identidad visual, el CSS ni se rediseñaron formularios.

Comandos efectivos (desde cada repositorio, con su entorno aislado):

    npm.cmd run test
    npm.cmd run lint
    npm.cmd run build
    npm.cmd run build -- --outDir <directorio-temporal-de-medicion>
    python manage.py check --settings=config.settings_test_mysql
    python manage.py makemigrations --check --dry-run --settings=config.settings_test_mysql

Resultados: lint/build correctos, incluido el build estándar final; Django sin incidencias; No changes detected. Advertencias no bloqueantes: VM Modules experimental en Node; outDir temporal fuera del frontend al construir las versiones de medición; conversión LF/CRLF advertida por Git. git diff --check sin errores. Se verificaron por SHA-256 138 archivos preexistentes ajenos a la corrección, sin cambios.

Pruebas MySQL, después de configurar GM_TEST_MYSQL_PORT para una instancia local y DJANGO_SETTINGS_MODULE=config.settings_test_mysql, con base gm_test_single_area vacía:

    python -c 'import django,unittest; django.setup(); suite=unittest.defaultTestLoader.loadTestsFromName("apps.projects.tests.test_performance.PerformanceRegressionTests"); result=unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(not result.wasSuccessful())'

El guard de la prueba rechaza una base no aislada o no vacía; no borra tablas preexistentes. Se crea y retira únicamente su fixture.

Suite SQLite: AUTH_TEST_SQLITE=1, DJANGO_SETTINGS_MODULE=config.settings, DJANGO_ALLOWED_HOSTS incluyendo testserver y claves sintéticas. Con django.setup() se cargaron vía unittest los módulos test_projects, test_segmentation, test_task_states, test_auth, test_integration y PerformanceRegressionTests.

Intentos fallidos y corregidos: el primer comando Django test con unittest.TextTestRunner no admite las opciones de Django; se usó el runner unittest con django.setup(). La primera ejecución SQLite omitió testserver de ALLOWED_HOSTS y falló por configuración (400); se corrigió exclusivamente el entorno del comando y se repitió la suite completa indicada. No se contaron esos intentos como aprobados.

## Archivos de esta corrección

Backend:

- apps/authentication/models.py, security.py, tokens.py y views.py.
- apps/workers/services/areas.py.
- apps/projects/services/projects.py y presentation.py.
- apps/projects/views.py.
- apps/projects/tests/test_performance.py.
- docs/performance_gestion_proyectos_primera_correccion.md.

Frontend:

- src/App.tsx.
- src/features/auth/api.ts.
- src/features/layout/AppShell/AppShell.tsx.
- src/features/projects/ProjectRoute/ProjectRoute.tsx.
- src/features/projects/ProjectWorkspace/ProjectWorkspace.tsx.
- tests/api.test.mjs y package.json.

Los demás archivos que ya figuraban modificados/no versionados antes de empezar pertenecen al trabajo previo, no a esta corrección.

## Pendientes y criterios de aceptación en el despliegue

1. Repetir HAR y cronómetros de contenido útil con roles reales autorizados, sin datos sensibles en el reporte, para conocer cuánto queda de los 5–10 / 3–5 segundos. Separar RTT navegador/API, API/MySQL, SQL y serialización.
2. Medir p50/p95 con datos representativos y servidor de producción. Estas tres repeticiones de navegador no permiten inferir percentiles fiables ni capacidad para 50 usuarios.
3. Completar el par antes/después de navegación posterior a Proyectos. Se verificó el retorno y ausencia de nuevos GET después, pero no hay una muestra comparable anterior en esta ejecución.
4. Los deltas de ScriptDuration/LayoutDuration de CDP se descartaron porque los contadores se reinician al cambiar de documento y daban valores negativos. No se afirma haber medido un tiempo puro de renderizado comparable.
5. Confirmar en staging privado que siguen cumpliéndose ≤15/≤25/≤12 consultas con el mismo tamaño y que un cambio de rol/área/membresía/flag se refleja en la siguiente solicitud; respuestas y datos visibles deben coincidir con el contrato anterior. Probar también CSRF, replay y logout.
6. Mantener como criterio frontend un GET por recurso simultáneo bajo Strict Mode, ninguna espera del workspace por /api/projects/, errores recuperables y ningún resultado reutilizado entre sesiones. No se adoptó un TTL que difiera revocaciones.

No hay objetivos de consultas incumplidos en el fixture. Siguen pendientes la latencia compartida, renderizado aislado comparable y la capacidad real. Redis continúa fuera del alcance: antes de evaluarlo hay que medir esos pendientes y especificar autorización e invalidación; esta corrección no necesitó caché de respuestas.
