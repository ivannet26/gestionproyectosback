# AGENTS.md

## Alcance

Estas indicaciones aplican al repositorio backend del sistema de GM Ingenieros y Consultores.

- Lee este archivo y revisa el código relacionado antes de modificarlo.
- Respeta el alcance solicitado y realiza únicamente los cambios necesarios.
- Conserva la arquitectura, los contratos de API y las convenciones existentes.
- Protege los cambios locales; no sobrescribas ni reviertas trabajo ajeno.
- No agregues funcionalidades, refactorizaciones o dependencias que no sean necesarias para la solicitud.

## Convenciones de código

- Usa nombres técnicos en inglés y textos visibles de la API en español, según los contratos existentes.
- Usa `PascalCase` para clases; `snake_case` para módulos, funciones y variables; y `UPPER_SNAKE_CASE` para constantes.
- Sigue PEP 8 y las convenciones configuradas en el proyecto.
- Usa anotaciones de tipo cuando mejoren la claridad.
- Mantén las funciones y clases enfocadas en una responsabilidad clara.
- Evita duplicar lógica y crear abstracciones sin reutilización real.
- Prefiere soluciones simples y explícitas.
- Captura excepciones específicas y no ocultes errores con valores predeterminados silenciosos.
- No dejes imports sin usar, logs de depuración ni código comentado.

## Organización por dominios

- Organiza cada dominio en su aplicación propietaria dentro de `apps/<domain>`, siguiendo los nombres y estructura ya establecidos.
- Mantén modelos, servicios, serializers, vistas, permisos, pruebas y migraciones junto al dominio responsable.
- Importa cada entidad desde su aplicación propietaria. No dupliques modelos para una misma tabla ni uses otra aplicación como ubicación permanente para entidades ajenas.
- Mantén las reglas de negocio en servicios reutilizables según el patrón existente; conserva vistas y ViewSets ligeros.
- Evita dependencias circulares entre aplicaciones.
- Conserva las etiquetas históricas de Django y las dependencias de migración aunque el paquete tenga un nombre distinto. No reescribas migraciones aplicadas para reorganizar carpetas.
- Mantén separados los roles globales y los roles propios de cada entidad o proyecto. Los roles globales vigentes son `ADMINISTRADOR` y `TRABAJADOR`; no agregues ni reasignes roles sin un requisito explícito.

## Django y Django REST Framework

- Usa serializers para validar, normalizar y transformar datos de entrada y salida.
- Mantén respuestas HTTP y errores con el formato establecido por el proyecto.
- Coloca autenticación, autorización y validación crítica en el backend; nunca confíes en validaciones de React.
- Aplica permisos por operación y por objeto. Deniega por defecto y limita las consultas al conjunto de datos autorizado.
- Conserva los contratos de API existentes salvo que la solicitud requiera cambiarlos.
- Usa transacciones para operaciones que deban completarse de forma atómica.
- No añadas autenticación, autorización ni transporte alternativos cuando ya exista un mecanismo apropiado.

## MySQL, esquema y migraciones

- Inspecciona los modelos, las tablas y el esquema vigente antes de proponer cambios de persistencia.
- Conserva nombres físicos, tipos, claves, índices, restricciones y relaciones existentes, salvo que el cambio esté solicitado y justificado.
- Usa Django ORM o consultas parametrizadas. Nunca concatentes SQL con datos del usuario.
- Respeta los procedimientos, vistas, triggers y transacciones existentes; no los evites ni los dupliques sin necesidad.
- No modifiques migraciones ya aplicadas.
- Crea migraciones nuevas con dependencias correctas y revisa su SQL e impacto antes de entregarlas.
- Usa migraciones de estado solo cuando el esquema físico ya corresponda exactamente y el cambio sea únicamente de estado o propiedad de modelos. No las uses para ocultar diferencias ni para reemplazar cambios físicos requeridos.
- No ejecutes migraciones ni escrituras contra Aiven, producción o bases compartidas sin autorización explícita para esa operación.
- No sustituyas MySQL silenciosamente por otra tecnología ni crees una estructura paralela para evitar el esquema existente.

## Seguridad y datos

- Exige autenticación por defecto. Las rutas públicas deben ser explícitas, limitarse a su propósito y usar las protecciones existentes.
- Valida autorización en cada solicitud y sobre cada objeto; no confíes en IDs, filtros ni permisos enviados por el cliente.
- Valida, normaliza y limita longitud y formato de las entradas en el servidor.
- Usa los mecanismos existentes para contraseñas, tokens, invitaciones y recuperación; no almacenes ni registres secretos en texto plano.
- Mantén CORS restringido a los orígenes autorizados. No desactives CSRF ni debilites autenticación o permisos para resolver errores.
- No expongas secretos, credenciales, tokens, enlaces de activación, datos personales innecesarios, trazas ni detalles de infraestructura en respuestas o logs.
- Lee credenciales y configuración sensible desde variables de entorno. No modifiques `.env`; documenta variables nuevas únicamente en `.env.example` con valores ficticios.
- Usa el mecanismo de auditoría existente para acciones sensibles, sin registrar contenido confidencial innecesario.
- No uses datos reales en pruebas o fixtures.

## Pruebas y calidad

- Escribe o ajusta pruebas sintéticas para las reglas de negocio, permisos, endpoints y casos de error afectados.
- Usa la configuración de pruebas aislada existente. No apuntes pruebas que escriben datos a Aiven ni a una base compartida.
- No sustituyas MySQL por SQLite silenciosamente. Usa SQLite solo cuando la prueba aislada existente lo configure explícitamente y sea adecuado para lo que se valida.
- Ejecuta las verificaciones pertinentes, como `python manage.py check`, pruebas dirigidas y comprobaciones de migraciones en modo no destructivo.
- No ejecutes suites completas no relacionadas si las pruebas dirigidas cubren el cambio.
- Informa únicamente las verificaciones realmente ejecutadas y sus resultados.

## Comentarios en el código

- No agregues comentarios de ningún tipo al código fuente: comentarios de línea o bloque, documentación inline, `TODO`, `FIXME` ni código comentado.
- Expresa la intención mediante nombres claros, funciones pequeñas y una estructura coherente.
- No hagas cambios masivos en archivos no relacionados para eliminar comentarios existentes.
- Registra decisiones técnicas y contexto temporal fuera del código, en la documentación pertinente.

## Flujo de trabajo y entrega

Antes de implementar:

1. Revisa el código, el esquema y las migraciones relacionados.
2. Identifica los archivos que realmente deben modificarse.
3. Si la tarea implica varios cambios, presenta un plan breve y continúa sin esperar confirmación, salvo que exista un bloqueo real.

Después de implementar:

1. Informa los archivos modificados.
2. Resume el comportamiento implementado y los endpoints afectados.
3. Indica las verificaciones ejecutadas y sus resultados.
4. Informa bloqueos, limitaciones y pendientes reales.

## Git

- Inspecciona el estado con comandos de lectura, como `git status` y `git diff`, cuando sea necesario.
- No ejecutes commits, push ni operaciones destructivas de Git. El usuario gestiona los commits y la publicación.