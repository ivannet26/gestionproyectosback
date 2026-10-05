# Revisión pendiente: invitaciones, áreas y roles

Estado: implementación preparada, migraciones sin aplicar en Aiven. No se consultaron cuentas, correos, contraseñas ni hashes de la base compartida. No se enviaron correos reales. El script SQL original y las carpetas `database/` y `docs/` permanecen sin cambios.

La nueva versión requiere el esquema de estas migraciones. No ponerla a atender solicitudes contra el esquema antiguo ni alternar instancias antiguas y nuevas durante la transición. Revisar y aprobar la aplicación por separado, con una ventana de mantenimiento y respaldo recuperable.

## Migraciones propuestas

| Archivo | Cambio | Impacto previsto en Aiven |
| --- | --- | --- |
| `apps/autenticacion/migrations/0001_initial.py` | Migración existente, no modificada. Mapea entidades operativas como no administradas y crea las tablas de tokens, recuperación y limitación de intentos. | Comprobar su estado de aplicación antes de continuar. No recrear las entidades existentes ni utilizar `--fake` sin comprobar el esquema. |
| `0002_worker_areas_invitations.py` | Hace nullable `trabajador.area_id`, conservando su tipo unsigned y FK existente; añade `todas_las_areas` y una restricción de coherencia; crea `trabajador_area`, `auth_invitation` y `auth_migration_backup`. | DDL sobre trabajador y tablas adicionales. Posibles bloqueos de metadatos. No cambia las áreas principales existentes. |
| `0003_final_roles_and_existing_areas.py` | Respalda catálogo, asignaciones globales y relaciones añadidas; convierte asignaciones globales COLABORADOR a TRABAJADOR, preservando Administrador; retira códigos obsoletos sin asignaciones; rellena relaciones desde las áreas actuales y restringe el catálogo final. | DML de transición y `CHECK` en `rol`. No modifica cuentas, credenciales, trabajadores ni roles de proyecto. |
| `0004_global_admin_sql_policy.py` | Guarda definiciones actuales, crea la vista de áreas autorizadas, amplía disponibilidad y sustituye dos procedimientos de autorización. | DDL de vistas y procedimientos. Precisa privilegios adecuados, revisión de definiciones y prueba previa en MySQL aislado. |

### Áreas específicas

- `todas_las_areas = 0`, con una o más relaciones únicas en `trabajador_area`.
- `area_id` conserva el primer valor elegido expresamente en el formulario, para compatibilidad. No se inventa ni asigna un área de respaldo arbitraria.
- Se copia el área principal de los trabajadores existentes a la relación, sin duplicar trabajadores ni alterar sus IDs.
- Las relaciones explícitas son la fuente del alcance. Solo para registros sin relaciones se utiliza el campo legado como compatibilidad. Cambios posteriores de áreas deben sincronizar relación y área principal; no deben escribir únicamente el campo legado.
- Solo áreas activas intervienen en la autorización. Tanto Django como la vista SQL centralizan esa resolución.

### Todas

- `todas_las_areas = 1`, `area_id = NULL`, sin enumerar relaciones individuales durante el registro.
- La vista `v_trabajador_area_autorizada` y `services/areas.py` resuelven todas las áreas activas en cada consulta. Las nuevas áreas activas quedan incluidas sin actualizar al trabajador.
- La restricción `ck_trabajador_alcance` impide combinaciones inconsistentes entre bandera y área principal.
- No se crea un área ficticia. La vista de disponibilidad sigue teniendo una fila por trabajador: no multiplica capacidad, horas ni disponibilidad por el número de áreas. Conserva sus columnas anteriores, admite `area_id` nulo y añade la bandera al final.
- Los consumidores futuros que filtren alcance por área deberán utilizar la resolución centralizada, no `v_disponibilidad_actual.area_id` por sí solo.

### Roles y datos existentes

- Catálogo global final: ADMINISTRADOR y TRABAJADOR. No hay compatibilidad funcional con COORDINADOR ni COLABORADOR en autenticación o interfaz.
- La cuenta Administrador conserva ID, nombre interno, trabajador, contraseña y asignación administrativa. Asignaciones redundantes conocidas de esa cuenta se respaldan antes de normalizar a Administrador.
- COLABORADOR global se transforma en TRABAJADOR conservando la cuenta. Las asignaciones inesperadas de COORDINADOR, GERENCIA, REVISOR o códigos desconocidos detienen la transición: requieren revisión explícita, no reclasificación automática.
- Los códigos obsoletos del catálogo solo se retiran después de comprobar que no existen asignaciones inesperadas. El respaldo permite restaurar el catálogo original cuando se cumplan las condiciones de reversión.
- `proyecto_miembro.rol_proyecto` y sus conceptos RESPONSABLE, REVISOR y COLABORADOR no se modifican.

## Rutinas SQL para revisar

Las definiciones propuestas están en `apps/autenticacion/migrations/sql/`. Los archivos `.before.sql` conservan los dos procedimientos del script recibido para facilitar comparación, no son la política que se instalará.

- `sp_validar_supervisor.sql`: Administrador activo puede supervisar globalmente sin membresía ni área del proyecto. Trabajador necesita ser RESPONSABLE activo del proyecto y tener su área autorizada.
- `sp_cambiar_estado_actividad.sql`: Administrador activo recibe supervisión global y no necesita membresía ni ser responsable de cada actividad. Trabajador conserva membresía, área autorizada y, según la transición, asignación de actividad o rol de supervisión del proyecto. No se cambian las reglas operativas de estados, motivos, responsables válidos, dependencias, subtareas o entregables.
- Ambas rutinas deniegan cuentas inactivas, trabajadores inactivos, roles desconocidos y múltiples roles globales. El Administrador no queda exento de las reglas de integridad y transición del proyecto o actividad.
- La migración compara los cuerpos de los procedimientos vivos con la referencia revisada y detiene cambios no previstos. También evita sobrescribir una vista de áreas autorizadas preexistente ajena a esta migración.
- Se respalda la definición completa de procedimientos y disponibilidad antes de reemplazarlos. Deben revisarse también la vista viva de disponibilidad, sus consumidores, `DEFINER`, `SQL SECURITY`, modos SQL y permisos del ejecutor. La sustitución usa `SQL SECURITY INVOKER`.
- No se añaden endpoints operativos de proyectos ni actividades. Una futura invocación SQL debe establecer `@gm_usuario_id` exclusivamente desde la identidad autenticada y limpiarlo en `finally` antes de devolver la conexión al pool. No tomarlo del payload del navegador.

## Comprobaciones previas a cualquier aplicación

1. Verificar metadatos e historial de migraciones: motor InnoDB, versión con `CHECK` efectivo, `area_id BIGINT UNSIGNED NOT NULL`, FK y restricciones vigentes. Revisar metadatos de las nuevas tablas, vistas y procedimientos para evitar colisiones. No consultar hashes ni listar datos personales para esta revisión.
2. Revisar conteos agregados de asignaciones por código global y comprobar la ausencia de Coordinador y de códigos inesperados asignados. Si aparecen, detenerse. No modificar registros reales para hacer pasar la validación.
3. Comparar las rutinas y vista vigentes con los archivos propuestos, revisar el impacto en los consumidores y validar DDL, FKs unsigned, restricciones y rutinas completas en una base MySQL descartable con datos sintéticos.
4. Disponer de un respaldo externo recuperable y detener escritores durante la transición. El respaldo interno de esta migración no sustituye al respaldo de la base.
5. Aprobar explícitamente el plan de aplicación y recuperación. Las operaciones DDL son no atómicas entre sentencias; un fallo parcial requiere revisar el estado y el respaldo antes de reintentar o revertir. No usar `--fake` para ignorar fallos.

MySQL admite `CHECK` efectivos desde 8.0.16 y limita su combinación con acciones referenciales; revisar las restricciones de la base real antes de aprobar. Referencias: [ALTER TABLE](https://dev.mysql.com/doc/refman/8.0/en/alter-table.html) y [CHECK Constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table-check-constraints.html).

### Reversión

La reversión restaura definiciones SQL y datos respaldados cuando no se han producido cambios posteriores incompatibles. Se detiene si cambiaron asignaciones originales, nuevas cuentas dependen del código TRABAJADOR, las rutinas cambiaron después de instalarlas, hay trabajadores con Todas/área nula, áreas adicionales o historial de invitaciones que se perdería. La conciliación y archivo necesarios deben aprobarse antes de continuar. No convertir Todas a un área arbitraria ni borrar historia para forzar la reversión.

## Flujo e interfaz

Registro exclusivo del Administrador: nombres, apellidos, correo, áreas y uno de dos roles. Las áreas se cargan desde `GET /api/auth/admin/areas/`. El primer selector permite Todas directamente; al elegirlo desaparecen selectores adicionales y el botón de agregar. Con áreas específicas no se ofrecen duplicados y solo se agrega un selector cuando quedan opciones y los anteriores están completos; los adicionales se pueden retirar.

Se crean trabajador, cuenta inactiva, rol y relaciones en una transacción. Código de trabajador y nombre interno de cuenta se generan en el servidor. El correo completo se conserva en trabajador y es el identificador del login, independiente del nombre interno limitado a 80 caracteres. Se usa el valor por defecto de capacidad semanal definido en el esquema original; no se añade teléfono ni ningún campo innecesario al formulario.

El correo se solicita después de confirmar la transacción. Solo una respuesta de Resend con identificador de envío se muestra como aceptación. Rechazo confirmado marca fallo y revoca el enlace; timeout o respuesta sin confirmación marca estado desconocido. La cuenta permanece pendiente y el reenvío usa la misma cuenta y un enlace nuevo, invalidando el anterior. La interfaz distingue aceptación del proveedor de entrega efectiva al buzón.

Activación muestra nombres, apellidos, correo, áreas y rol de solo lectura obtenidos del servidor. Solo contraseña y confirmación son editables. React comprueba longitud y coincidencia y consulta la validación del backend antes de completar; Django comprueba al menos 12 caracteres, claves comunes, similitud con los datos personales y claves exclusivamente numéricas en ambos endpoints. El endpoint final repite la validación y rechaza cualquier campo adicional. El enlace está vinculado a la cuenta y al digest de su correo actual, expira y solo puede consumirse una vez. La contraseña se guarda mediante Django; la activación y recuperación revocan tokens previos.

## Endpoints

Todos usan prefijo `/api/auth/`. Los endpoints `admin/` requieren Administrador en el backend.

| Método | Ruta | Función |
| --- | --- | --- |
| GET | `csrf/` | Cookie y token CSRF para bootstrap autorizado. |
| POST | `login/`, `refresh/`, `logout/` | Login por correo, renovación con límite original y cierre; protegidos por CSRF. |
| GET | `me/` | Perfil, alcance y permisos del usuario autenticado. |
| GET | `admin/areas/`, `admin/accounts/` | Áreas activas y cuentas con estado de invitación. |
| POST | `admin/invitations/` | Registro atómico e invitación. |
| POST | `admin/accounts/<id>/resend-invitation/` | Reenvío sin cambiar datos ni duplicar cuenta. |
| POST | `activate/preview/`, `activate/validate-password/`, `activate/` | Datos de solo lectura, validación y activación. |
| POST | `recovery-requests/` | Solicitud genérica, sin revelar existencia del correo. |
| GET / POST | `admin/recovery-requests/`, `admin/recovery-requests/<id>/issue/` | Bandeja y emisión administrativa de restablecimiento. |
| POST | `reset/preview/`, `reset/validate-password/`, `reset/` | Comprobación del enlace, validación y cambio de contraseña. |

Se conservan access tokens en memoria del frontend, refresh únicamente en cookie HttpOnly, CSRF y CORS explícito. El refresh vence el lunes siguiente a las 00:00 de America/Lima, con máximo de siete días y sin extender el plazo al renovar. El access por defecto dura 15 minutos y no supera el fin de la sesión.

## Configuración y correo real pendiente

Reutilizar las variables de `backend/.env.example`, sin versionar secretos:

- `DJANGO_SECRET_KEY`, `AUTH_JWT_KEY`: secretos distintos y estables. Rotar la clave JWT invalida sesiones y enlaces existentes.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSL_MODE`: conexión existente; no se cambió ni se utilizó Aiven en las pruebas.
- `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `FRONTEND_ORIGIN`, `FRONTEND_URL`, `AUTH_COOKIE_SAMESITE`: localhost para desarrollo y HTTPS con origen explícito en producción. La cookie es Secure fuera de desarrollo; si frontend y API son cross-site se requiere revisar política SameSite y compatibilidad del navegador, sin deshabilitar CSRF.
- `AUTH_ACCESS_MINUTES`, `AUTH_LINK_HOURS`, `AUTH_RESET_MINUTES`: valores iniciales 15 minutos, 24 horas y 30 minutos.
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`: configurar clave válida y remitente de dominio verificado/autorizado. Después de aprobar migraciones, comprobar el envío con un destinatario de prueba autorizado, nunca un trabajador real sin consentimiento.
- Frontend: `VITE_API_BASE_URL` apuntando a la API. Se mantienen las rutas `/activar`, `/restablecer`, `/recuperar` y `/administracion/cuentas`; el servidor de producción debe servir React también en esas rutas.

## Validación ejecutada

- 43 pruebas enfocadas con SQLite en memoria y datos sintéticos, sin llamadas a Resend: autenticación, permisos, inactividad, límite de intentos, cookies/CSRF/CORS, registro, unicidad, correo largo, áreas específicas/Todas/futuras, readonly, contraseña, tokens expirados/reutilizados/reemitidos, fallos de envío y reintentos; transición y reversión de datos, guardas y estructura de política SQL.
- `manage.py check`: sin incidencias.
- `manage.py makemigrations autenticacion --check --dry-run`: sin cambios pendientes de estado.
- `npm run lint` y `npm run build`: correctos.
- No se ejecutó `migrate`, DDL ni DML en Aiven. Los tests de DDL utilizan dobles y los tests de política SQL comparan las definiciones: no son una ejecución de los procedimientos completos en MySQL.
- No se realizaron pruebas manuales extensas de interfaz ni envío real. El usuario validará la experiencia visual; la revisión y ensayo de las migraciones completas en MySQL aislado sigue pendiente.

## Archivos de esta actividad

Backend: `config/settings.py` (política mínima de contraseña); `apps/autenticacion/models.py`, `serializers.py`, `views.py`, `urls.py`, `security.py`, `tokens.py`, `mail.py`; `services/__init__.py`, `services/areas.py`, `services/accounts.py`; migraciones 0002–0004 y sus SQL; pruebas `test_auth.py`, `test_integration.py`, `test_migrations.py`, `test_mail.py`; este documento.

Frontend: `src/auth/InvitationForm.jsx`, `AdminAccountsPage.jsx`, `AuthPages.jsx`, `api.js`, `roles.js`; `src/components/Sidebar.jsx`; `src/App.css`.

Se conservaron los cambios locales preexistentes, incluido el resto del dashboard, estilos, AGENTS, requisitos y configuración. No se instalaron dependencias ni se hicieron commits o push.
