# Seguridad de acceso

Este incremento protege la recuperación del personal y revoca sus sesiones
cuando cambia la contraseña o se desactiva la cuenta. No cierra aún la revisión
de seguridad de pagos, chat, evidencias ni infraestructura.

## Actualización de una instalación existente

La base debe tener las tablas del proyecto, incluida `recuperacion_contrasenas`
de la migración 004. Detener los procesos web de la versión anterior y obtener
un respaldo antes de ejecutar, desde la raíz del repositorio:

```powershell
py -m app.core.migrations --desde 005
```

Se agregan `usuarios.version_sesion`, `recuperacion_contrasenas.codigo_hash`,
`recuperacion_contrasenas.intentos_fallidos` y la tabla `limites_recuperacion`.
Los OTP anteriores se borran e invalidan; las contraseñas del personal se
conservan. Las sesiones de la versión anterior no tienen versión y deben
autenticarse nuevamente. No es compatible mantener procesos de la aplicación
anterior ejecutándose durante la actualización.

La migración se puede reanudar si el proceso se interrumpe: comprueba la
existencia de cada columna antes de crearla. No invalida los códigos nuevos
al repetirse. Esta migración no se ejecuta automáticamente al arrancar.

Para una instalación vacía, el script `scripts/init_database.sql` ya incluye
esta estructura. Sus usuarios semilla corresponden a una demostración; la
preparación de credenciales de producción sigue pendiente en el plan.

## Reglas implementadas

- Seis dígitos criptográficamente aleatorios, quince minutos de vigencia y
  un solo uso. La referencia temporal es MySQL, no el reloj del navegador.
- HMAC-SHA256 del OTP ligado al usuario y a `SECRET_KEY`. La columna legacy
  `codigo` se guarda vacía; no se compara ni admite un OTP antiguo en claro.
- Presupuesto compartido en base: cinco emisiones por cuenta y hora, con
  un minuto entre emisiones. Un rechazo no reemplaza el OTP vigente.
- Cinco verificaciones incorrectas por código, persistidas aunque la
  solicitud sea rechazada. Al agotarlas se invalida el código, sin bloquear
  el inicio de sesión de la cuenta.
- Cuenta ausente, inactiva o limitada recibe el mismo mensaje público de
  solicitud. La uniformidad temporal de las respuestas sigue pendiente.
- La clave cambia junto a la invalidación del OTP y el aumento de versión
  de sesión en una transacción. El usuario y el OTP se bloquean en ese orden.
- Cada petición autenticada comprueba estado, versión y rol actuales en
  base. Una desactivación o cambio de contraseña invalida las sesiones
  anteriores en su próxima petición. Reactivar no revive sesiones antiguas.
- El login borra datos de la sesión anterior y renueva el identificador.
- Sin sesión, las APIs devuelven 401; sin permiso, 403; si no se puede
  verificar el acceso por un fallo de persistencia, 503. No ejecutan la acción.
- Una contraseña admite al menos ocho caracteres, una letra y un número,
  y como máximo 72 bytes UTF-8 para evitar truncamiento de bcrypt.

`SECRET_KEY` debe ser privada, estable y compartida por los procesos de la
misma instalación. Rotarla invalida los OTP pendientes y reinicia las claves
de los contadores por cuenta. Los límites por IP siguen usando el backend
actual en memoria; su persistencia compartida queda para el despliegue.

El envío SMTP conserva el mecanismo asíncrono existente: falta una cola
persistente y confirmación de entrega. Si SMTP falla, el código no se muestra
en la web como alternativa. También queda por definir la limpieza programada
de registros de recuperación y contadores sin actividad.

## Verificación

Se ejecutaron 130 pruebas de seguridad y regresión, con dos pruebas ajenas
al bloque deseleccionadas. Diez pruebas usaron MariaDB 10.4/InnoDB en una
instancia desechable y comprobaron migración, reejecución, límites,
revocación y concurrencia. No certifica todavía MySQL 8 en el hosting final.
No se utilizaron correos ni cobros reales en las pruebas. Después de validarlas,
se aplicó la migración 005 a la base local, con un respaldo restaurado en la
instancia temporal y recuentos coincidentes en todas las tablas.

Las pruebas de integración se omiten por defecto. Para una instancia local
exclusiva de pruebas en un puerto distinto de 3306:

```powershell
$env:FORMOPACK_TEST_DB_PORT='23316'
py -B -m pytest -q -p no:cacheprovider tests/test_seguridad_bd.py
```

El fixture crea y elimina solamente bases con un nombre aleatorio
`formopack_test_…`. La instancia debe iniciarse aparte; el puerto del ejemplo
no implica que exista un servidor permanente allí.

Referencias: [OWASP Recuperación](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
[Flask-Session Seguridad](https://flask-session.readthedocs.io/en/latest/security.html).
