# AGENTS.md

## Alcance

Estas reglas aplican a todo el código del sistema de GM Ingenieros y Consultores.

- Respetar la solicitud y el alcance de cada tarea.
- Revisar el código relacionado antes de modificarlo.
- Modificar únicamente lo necesario para cumplir la tarea.
- No introducir funcionalidades, refactorizaciones ni dependencias no solicitadas.
- Reutilizar las convenciones y componentes existentes cuando sean adecuados.
- Mantener el código legible, predecible y fácil de mantener.

## Convenciones generales

- Usar nombres técnicos en inglés y textos visibles de la interfaz en español.
- Usar `PascalCase` para clases y componentes.
- Usar `camelCase` para variables, funciones, propiedades y métodos en JavaScript.
- Usar `snake_case` para variables, funciones y módulos de Python.
- Usar `UPPER_SNAKE_CASE` para constantes.
- Evitar abreviaturas ambiguas, nombres genéricos y valores mágicos.
- Mantener funciones y componentes pequeños, con una responsabilidad clara.
- Evitar duplicación de lógica; extraer utilidades solo cuando exista reutilización real.
- Preferir soluciones simples y explícitas antes que abstracciones innecesarias.
- No dejar código comentado, logs de depuración ni imports sin utilizar.
- Los comentarios deben explicar decisiones o restricciones, no repetir el código.

## Python, Django y Django REST Framework

- Seguir PEP 8 y las convenciones existentes del proyecto.
- Preferir funciones y clases con nombres descriptivos.
- Usar anotaciones de tipo cuando mejoren la claridad sin forzar complejidad.
- Mantener las vistas y ViewSets ligeros; la lógica de negocio compleja debe estar en servicios reutilizables.
- Usar serializers para validar y transformar los datos de entrada y salida.
- Aplicar permisos y validaciones en el backend; nunca confiar únicamente en la interfaz.
- Mantener respuestas HTTP y errores con un formato uniforme.
- Capturar excepciones específicas; evitar `except Exception` salvo que exista una razón documentada.
- No ocultar errores reales con valores predeterminados silenciosos.
- Separar validación, lógica de negocio y presentación de datos.
- Escribir pruebas para reglas de negocio, endpoints y casos de error relevantes.

## React y JavaScript

- Usar componentes funcionales y Hooks.
- Nombrar los componentes con `PascalCase` y los Hooks personalizados con el prefijo `use`.
- Mantener cada componente enfocado en una responsabilidad.
- Recibir datos mediante props explícitas y evitar dependencias ocultas.
- Centralizar las llamadas HTTP y no mezclarlas innecesariamente con componentes visuales.
- Mantener separados los datos simulados, la lógica de presentación y la comunicación con la API.
- Usar estado local por defecto; elevarlo o compartirlo solo cuando sea necesario.
- Evitar usar `useEffect` para calcular valores derivados que puedan obtenerse directamente.
- Usar claves estables al renderizar listas.
- Controlar estados de carga, error, vacío y éxito cuando corresponda.
- No mutar directamente estados, props ni objetos compartidos.
- Preferir HTML semántico, etiquetas asociadas a campos y navegación accesible por teclado.

## Validación y calidad

- Validar entradas tanto en la interfaz como en el backend, sin duplicar reglas críticas de forma inconsistente.
- Mostrar errores comprensibles al usuario y conservar detalles técnicos en los registros apropiados.
- Mantener funciones deterministas cuando sea posible.
- Evitar efectos secundarios ocultos y dependencias globales innecesarias.
- Antes de finalizar, revisar formato, imports, warnings y errores de consola.
- Ejecutar las pruebas y verificaciones disponibles para el código modificado.
- Verificar que la compilación o ejecución local funcione correctamente.
- No considerar terminada una tarea si existen errores conocidos sin informar.

## Seguridad del código

- No incluir contraseñas, tokens, claves ni datos sensibles en el código fuente.
- No confiar en datos provenientes del cliente.
- Validar entradas y controlar permisos antes de ejecutar operaciones sensibles.
- Evitar exponer información interna en mensajes de error visibles.
- No utilizar código dinámico o ejecuciones arbitrarias sin una justificación estricta.

## Entrega de cada tarea

Antes de implementar:

1. Revisar el código relacionado.
2. Identificar los archivos que realmente deben modificarse.
3. Presentar un plan breve si la tarea involucra varios cambios.

Después de implementar:

1. Informar los archivos modificados.
2. Resumir el comportamiento implementado.
3. Indicar las validaciones ejecutadas.
4. Informar errores, limitaciones o pendientes reales.


## Seguridad web y datos operativos

- Aplicar mínimo privilegio y denegar el acceso por defecto.
- Exigir autenticación en endpoints privados y validar autorización en el backend para cada operación y cada objeto.
- Filtrar proyectos, áreas, trabajadores, tareas y subtareas según rol, áreas autorizadas y participación; no confiar en controles ocultos ni IDs enviados por el cliente.
- Validar, normalizar y limitar longitud/formato de toda entrada en el servidor.
- Usar Django ORM o consultas parametrizadas; nunca concatenar SQL con datos del usuario.
- Evitar XSS: no insertar contenido del usuario como HTML ni usar `dangerouslySetInnerHTML` sin sanitización justificada.
- No exponer secretos, datos personales innecesarios, trazas internas ni detalles de infraestructura en respuestas o logs.
- Mantener CORS restringido a orígenes autorizados; no desactivar CSRF ni debilitar autenticación para resolver errores.
- No almacenar credenciales en el repositorio, frontend, logs o respuestas; mantenerlas en variables de entorno y usar `.env.example` con valores ficticios.
- Tratar proyectos publicados como información interna; nunca hacerlos accesibles sin autenticación salvo requisito explícito aprobado.
- Registrar actor y acción en cambios sensibles mediante el mecanismo de auditoría existente, sin copiar contenido confidencial innecesariamente.
- Probar permisos y aislamiento entre áreas con datos sintéticos; nunca usar datos reales en fixtures o pruebas.
- No ejecutar migraciones destructivas ni escrituras contra producción o bases compartidas sin autorización explícita y revisión previa.

## Comentarios en el código

- No agregar comentarios de ningún tipo dentro del código fuente: comentarios de línea, bloque, documentación inline, `TODO`, `FIXME` ni código comentado.
- Todo código nuevo o modificado debe quedar libre de comentarios.
- El código debe ser comprensible mediante nombres claros, funciones pequeñas y una estructura coherente.
- Las explicaciones técnicas, decisiones y reglas deben registrarse fuera del código, en `AGENTS.md` o en la documentación correspondiente.
- No realizar cambios masivos en archivos no relacionados únicamente para eliminar comentarios existentes.

## Organización por dominios y entidades

- Cada aplicación debe ser propietaria de los modelos, servicios, validaciones, endpoints, pruebas y migraciones de su dominio.
- Importa cada entidad desde su aplicación propietaria. No dupliques modelos ni uses otra aplicación como ubicación permanente para entidades ajenas.
- Mantén las reglas de negocio junto al dominio responsable y evita dependencias circulares entre aplicaciones.
- Al reorganizar código, conserva los contratos existentes de API y el comportamiento funcional, salvo que la tarea solicite cambiarlos.
- Si una entidad se mapea a una tabla existente, conserva nombres de tablas y columnas, tipos, claves, restricciones y relaciones, salvo cambio expresamente requerido.
- No modifiques migraciones ya aplicadas. Las nuevas migraciones deben respetar el grafo existente y distinguir claramente cambios de estado de cambios físicos en la base de datos.
- Usa migraciones solo de estado cuando el esquema físico ya corresponda exactamente y el cambio sea únicamente de propiedad o estado de modelos en Django. No las uses para ocultar diferencias ni para sustituir la creación o corrección de tablas.
- Antes de proponer una migración, revisa sus dependencias, operaciones, SQL generado y compatibilidad con el historial existente. Documenta su impacto y las verificaciones pendientes.
- Mantén `AGENTS.md` como guía permanente de codificación; registra el estado temporal de módulos y migraciones en documentación de revisión.
- No incluyas comentarios en el código.