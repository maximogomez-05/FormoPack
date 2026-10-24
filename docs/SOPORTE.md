# Soporte uno a uno — RF 5.6

Incremento del 24 de octubre de 2026. Se toma como referencia el RF y la
descripción de la secuencia del documento académico: finalizar conserva el
registro de atención y elimina los mensajes. El diagrama actual que indica
este comportamiento queda pendiente de actualizar con los detalles implementados.

## Comportamiento y responsabilidades

`ChatSoporte` determina quién puede leer, tomar, responder y finalizar.
`MensajeSoporte` valida texto no vacío de hasta 2000 caracteres.
`SoporteController` coordina persistencia, bloqueos y transacciones; las rutas
resuelven identidad, presentación y respuestas HTTP.

- Un operador activo, recepcionista o administrador, atiende un chat a la vez.
  La toma bloquea usuario y chat. Una columna generada e índice único impiden
  asignaciones duplicadas incluso si se omite el controlador.
- Cualquier operador puede consultar la cola sin atender. Una conversación
  asignada solo permite responder al responsable. Otros recepcionistas no
  pueden leer sus mensajes ni finalizarla; el administrador puede supervisar
  y cerrar, pero no responder como si fuera el responsable.
- El cliente puede finalizar su propia conversación. Cierre y purga se guardan
  juntos; si falla la actualización, se revierten también los mensajes borrados.
  Repetir el cierre no reemplaza su fecha ni responsable.
- El registro cerrado conserva cliente, guía, operador asignado y fechas. Si
  cierra personal, también registra su identificador. Los cerrados salen del
  panel activo. El cierre del cliente deja `id_usuario_cierre` en NULL.
- La identidad pública se guarda en la sesión del servidor. No se admite un
  `session_id` enviado por el cliente ni se devuelve el identificador secreto.
  El navegador solo almacena un indicador de interfaz; necesita su cookie de
  sesión para recuperar el chat. Las sesiones antiguas basadas en un token en
  sessionStorage no se adoptan; el usuario puede iniciar una nueva conversación.
- Todos los POST requieren CSRF. Se limitan los inicios a cinco por minuto/IP,
  envíos a treinta por minuto/sesión, consultas a sesenta y cierres a diez.
  Nombre, correo, guía y mensaje se validan en servidor. El HTML dinámico
  escapa los textos y no borra el borrador ante errores de envío.

## Actualización de la base

Con la aplicación detenida y respaldo comprobado:

```powershell
py -m app.core.migrations --desde 006
```

Requiere el esquema de soporte existente. La migración agrega el estado
`cerrado`, `fecha_cierre`, `id_usuario_cierre`, la columna generada
`operador_activo` y su índice único. Las referencias al personal usan RESTRICT:
su baja es lógica y el historial conserva sus responsables. Los chats activos
sin responsable vuelven a la cola. Si un operador tiene varios chats activos,
el gestor detiene la migración antes de cambiar el esquema; se deben resolver
las asignaciones explícitamente. No reasigna ni cierra conversaciones por su cuenta.

El SQL admite reejecución y el inicializador completo incluye el cambio. No se
crean ni alteran tablas desde el controlador de soporte al arrancar la aplicación.
Se verificó con MariaDB 10.4.32; MySQL 8 requiere validación en el motor elegido
para el despliegue.

La base local fue actualizada después de restaurar un respaldo y comparar los
conteos de las 19 tablas en una instancia aislada. Respaldo fuera del repositorio:
`C:\Users\maxig\.codex\backups\formopack\soporte-20261024-200408.sql`.

## Verificación y límites

`tests/test_soporte.py` cubre dominio y HTTP sin datos operativos.
`tests/test_soporte_bd.py` cubre MariaDB, permisos, carreras concurrentes,
restricción SQL, inicio repetido, cierre y rollback ante fallo forzado.
`tests/test_soporte_navegador.py` y `tests/browser/soporte.cjs` verifican con
Chrome el inicio público, aislamiento entre clientes, autenticación, atención,
respuesta, conservación del borrador ante HTTP 503 y cierre con purga.

Las pruebas de base requieren una instancia local exclusiva, puerto distinto
de 3306, indicado mediante `FORMOPACK_TEST_DB_PORT`. Crean y eliminan solo bases
con nombres aleatorios de prueba. El recorrido de navegador requiere además
`FORMOPACK_TEST_NODE`, `FORMOPACK_TEST_PLAYWRIGHT` y, si se usa Chrome instalado,
`FORMOPACK_TEST_CHROME`. No ejecutar las pruebas antiguas que modifican la base
operativa como sustituto de esta selección aislada.

La selección de regresión acumulada pasó 173 pruebas, con dos deseleccionadas.
También se comprobó por separado la instalación completa desde cero, su
reejecución y la aplicación de migraciones sin reabrir un chat cerrado.
Quedan para despliegue las sesiones y límites compartidos entre procesos,
HTTPS, retención de registros cerrados, limpieza de chats abandonados y medidas
adicionales contra abuso. La limitación por IP puede afectar a clientes que
comparten conexión. La entrega de mensajes sigue usando consultas periódicas.
Perder la cookie de sesión impide recuperar la conversación pública anterior.

## Cambios que deberán reflejar los diagramas

- DER: columnas nuevas, índice de exclusividad y referencias al personal que
  conservan responsables históricos. `operador_activo` es derivado.
- Clases: entidades de políticas y mensaje, operaciones reales del controlador,
  identidad pública y presentación HTTP. No inventar herencias inexistentes.
- Casos de uso: cliente público sin cuenta; personal autenticado; responsable
  exclusivo, supervisión administrativa y cierre permitido a cada actor.
- Secuencias: bloqueos y conflicto al tomar, CSRF y sesión del servidor,
  persistencia de mensaje antes de confirmar, cierre/purga atómicos y rollback.
  El registro cerrado permanece y los mensajes se eliminan.

Los archivos gráficos no se modificaron en este incremento.
