# Primer acceso, inicio y actividad compacta

26 de octubre de 2026. Ajustes solicitados sobre navegación, seguridad e interfaz.

## Contraseña personal obligatoria

En la versión revisada no existía una obligación de cambio en el primer acceso.
Ahora `UsuarioController.crear_usuario` registra las altas con
`debe_cambiar_password=1`. La contraseña provisoria mantiene la política vigente:
al menos ocho caracteres, una letra y un número, y máximo de 72 bytes UTF-8.
`1234` no se admite como clave provisoria ni personal.

El login lee la marca desde la base y deriva a `/primer-acceso`, una tarjeta
dedicada que no se puede cerrar para seguir trabajando. `ControlSesion` refresca
el estado en cada petición y el control global impide acceder a otras pantallas
o APIs antes de completar el cambio. Las APIs devuelven HTTP 423 con
`PASSWORD_CHANGE_REQUIRED` y la URL de cambio. Se permiten la pantalla de cambio,
salida de sesión, recursos estáticos y webhook autenticado mediante firma propia.
El formulario exige CSRF y limita los intentos por IP.

`AuthController.cambiar_password_inicial` verifica sesión vigente, cuenta activa,
marca pendiente y contraseña provisoria. Rechaza reutilizarla, contraseñas débiles
y confirmaciones distintas. Con bloqueo del usuario, guarda el hash de la nueva
clave, limpia la marca, aumenta la versión de sesión e invalida OTP pendientes
en una transacción. Tras commit se renueva el identificador de la sesión actual;
las demás quedan revocadas en su próxima petición. La aplicación no muestra al
administrador la contraseña nueva ni guarda valores en claro.

Una recuperación por OTP verificado también permite establecer una contraseña
personal y limpia la obligación. Esto evita un segundo cambio redundante tras
la recuperación. Ninguna respuesta vuelve a completar campos de contraseñas.
Tampoco se permite conservar la clave provisoria mediante ese camino de recuperación.

La migración 008 agrega la marca con valor cero para cuentas existentes. No
restablece contraseñas ni obliga a repetir el proceso a los usuarios actuales.
Una cuenta creada antes de esta migración no se presume automáticamente pendiente.

## Navegación y actividad

Tracking público incorpora una casita con texto **Inicio**. Para visitantes lleva
a la presentación; para personal autenticado, al panel correspondiente a su rol.
El encabezado de las pantallas operativas también ofrece Inicio. El icono usa SVG
local y sigue visible aunque no cargue la fuente de iconos externa.

La actividad conserva los siete días consecutivos en sus datos. `ActividadOperativa`
presenta por defecto solo los días que tuvieron registros, entregas, incidencias
o importe facturado; no elimina ni modifica datos. **Ver los 7 días** muestra
también los días en cero y **Con movimiento** devuelve la vista compacta.
La selección mantiene los filtros de búsqueda del panel.

Si no hubo actividad se muestra un estado vacío compacto, sin gráfico ni tabla
vacíos grandes. El encabezado indica cuántos días tuvieron movimiento. Los errores
SQL del histórico ya no se convierten silenciosamente en ausencia de movimientos:
se propagan como indisponibilidad controlada. El gráfico representa nuevos
registros; la tabla conserva las otras métricas del día.

Los cambios mantienen el estilo existente, el contraste y el movimiento reducido.
Se inspeccionaron vistas de escritorio, móvil y primer acceso y se comprobó la
navegación desde tracking con y sin sesión.

## Migración y validación

Con respaldo y aplicación detenida:

```powershell
py -m app.core.migrations --desde 008
```

La base local se respaldó, restauró en la instancia aislada y cotejó en sus
20 tablas antes de aplicar la migración. Después se comprobó que contraseñas,
versiones de sesión y estado de cuentas existentes no cambiaron.
Respaldo fuera del repositorio:
`C:\Users\maxig\.codex\backups\formopack\primer-acceso-20261026-003546.sql`.
El servidor local se reinició y respondió correctamente en el puerto 5050.

Pruebas nuevas: `tests/test_primer_acceso.py` y
`tests/test_primer_acceso_navegador.py`, con `tests/browser/primer_acceso.cjs`.
Cubren los tres roles, clave incorrecta/repetida/débil, OTP, URLs y APIs,
revocación de otro navegador, concurrencia, rollback, migración, actividad,
navegación y alta administrativa seguida del cambio real en Chrome.
Usan exclusivamente las bases aleatorias y variables de prueba ya documentadas.
La selección acumulada aprobó 329 pruebas, con dos deseleccionadas, incluidos
los recorridos previos de soporte, recepción y pagos simulados. Las pruebas
adicionales de OTP se repitieron después de impedir reutilizar la clave provisoria.

Esta revisión no certifica el aislamiento de caché y cola offline entre usuarios:
ese trabajo continúa pendiente en el bloque PWA del plan. Tampoco completa pagos
en sandbox real ni los requisitos de logística/cobro en destino.

## Diagramas pendientes

DER: agregar la marca de primer acceso en usuarios. Clases: propiedad de Usuario,
operación de cambio inicial y presentación de actividad. Secuencia de login:
marca persistente, sesión restringida, validación y transacción de cambio,
rotación de sesión y revocación de las otras. Los gráficos se editarán al final.
