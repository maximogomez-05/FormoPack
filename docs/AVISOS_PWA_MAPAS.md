# Avisos operativos, PWA y seguimiento

Los cambios no modifican tarifas, pagos, caja, intentos de entrega ni devolución al remitente.
No se recrean avisos antiguos ni se envían correos a partir de datos históricos al migrar.

## Cola de correo

La migración `016_notificaciones.sql` agrega una tabla InnoDB. El alta del envío y cada
registro logístico agregan sus avisos con el mismo cursor y transacción del historial.
Un fallo al escribir el aviso revierte esa operación. La confirmación de una operación
no depende de la disponibilidad de SMTP. Direcciones ausentes o inválidas se omiten;
no se registran direcciones, cuerpo, claves ni respuestas SMTP en los logs del procesador.

La clave única deriva del evento de historial y del destinatario normalizado. Ambos roles
con el mismo correo reciben un solo aviso. Se congela el estado del evento para que una
cola demorada no confunda estados posteriores. El resumen manual de alertas se deduplica
por selección, día y destinatario y la interfaz informa que quedó programado.

El procesador separado reclama con token y vencimiento de cinco minutos, reintenta
transacciones que InnoDB interrumpe por concurrencia y confirma mediante ese mismo token.
No mantiene una transacción abierta durante SMTP. Un trabajo interrumpido puede volver
a reclamarse cuando vence. El servicio tiene un límite de cuatro minutos; systemd evita
superponer ejecuciones de su timer. Dos procesadores independientes también respetan
el bloqueo de cada trabajo. No lanzar procesos personalizados sin límite de ejecución.

Se hacen hasta cinco intentos, con esperas de 60, 120, 240 y 480 segundos; la indisponibilidad
puede alargar la entrega. Un rechazo de destinatario definitivo marca `fallido`.
Faltando credenciales, la herramienta termina sin consumir intentos. El socket SMTP tiene
timeout de 15 segundos y valida TLS. La cola no procesa códigos OTP: la recuperación
conserva su circuito separado, con espera acotada y sin registrar el código en logs.

SMTP no garantiza exactamente una entrega. Si el proveedor acepta el mensaje y el proceso
muere antes de guardar `enviado`, se puede repetir. El Message-ID estable permite identificar
ese caso, pero el proveedor puede no deduplicarlo. Un aviso `enviado` significa aceptado
por SMTP; no prueba lectura ni entrega a la bandeja principal.

## Actualización del VPS

Aplicar después de respaldar, sin cambiar los permisos DML del usuario de la aplicación:

```bash
cd ~/formopack-app &&
sudo /usr/local/sbin/formopack-backup &&
git pull --ff-only &&
sudo mariadb formopack_db < scripts/migrations/016_notificaciones.sql &&
sudo install -m 644 scripts/vps/formopack-notificaciones.service /etc/systemd/system/formopack-notificaciones.service &&
sudo install -m 644 scripts/vps/formopack-notificaciones.timer /etc/systemd/system/formopack-notificaciones.timer &&
sudo systemctl daemon-reload &&
sudo systemctl restart formopack &&
sudo systemctl enable --now formopack-notificaciones.timer
```

El SQL es repetible y no cambia los datos existentes. El ejecutor SQL administrativo
es distinto al usuario limitado de la aplicación. El worker lee el `.env` privado desde
el directorio del proyecto usando la configuración existente. No copiar secretos a Git
ni al archivo de unidad. El respaldo existente incluye la nueva tabla automáticamente.

Comprobar:

```bash
systemctl is-active formopack formopack-notificaciones.timer
systemctl list-timers formopack-notificaciones.timer --no-pager
.venv/bin/python scripts/procesar_notificaciones.py --resumen
sudo journalctl -u formopack-notificaciones.service -n 20 --no-pager
curl -f -s -o /dev/null -w '%{http_code}\n' https://formopackexpress.tech/
```

`--resumen` solo cuenta estados y no envía nada. El servicio oneshot puede figurar
inactivo entre ejecuciones correctas; comprobar el timer y el resultado del último trabajo.
Para revisar fallidos, consultar únicamente id, estado, intentos y ultimo_error. Después de
corregir la causa se puede reactivar un id concreto desde MariaDB administrativa:

```sql
UPDATE notificaciones_operativas SET estado='pendiente',intentos=0,disponible_en=NOW(),
 token=NULL,bloqueo_hasta=NULL,ultimo_error=NULL
 WHERE id_notificacion=ID_REVISADO AND estado='fallido';
```

No volver a pendientes todos los avisos ni alterar registros enviados. Los encolados nuevos
dependen de la tabla: si se revierte código, conservarla. No eliminarla como rollback.

## PWA y mapas

El identificador y el inicio de la PWA son `/chofer`; el scope `/` permite su service worker
actual. Los iconos de 192/512 y la variante maskable reutilizan la caja corporativa y la
variante maskable respeta la zona segura. La caché estática v6 reemplaza solamente cachés
estáticas anteriores; no modifica IndexedDB ni borra fotos, firmas u operaciones pendientes.
Se mantiene la caché privada de panel separada y vinculada al chofer.

Los dos mapas acotan las consultas a ocho segundos, impiden superposición, descartan
respuestas canceladas y reanudan consultas al recuperar visibilidad. Una señal con más de
cinco minutos deja de ser GPS actual incluso si la red está caída. Las fechas sin offset de
MariaDB se interpretan como Formosa (UTC-3), independientemente del dispositivo visitante.
En el mapa operativo se conserva la posición como última conocida con su fecha; en el público
se retira el marcador y se distingue ausencia de señal, vencimiento y conexión fallida.
Los estados terminales no inician consultas periódicas de GPS público. OSRM inválido,
incompleto o lento da paso a una línea referencial, sin representar el recorrido real.

Las pruebas usan MariaDB temporal, SMTP simulado y Chrome con proveedores interceptados.
La emulación no sustituye instalar/suspender la PWA en un teléfono real. Tampoco garantiza
GPS continuo con el navegador cerrado. No se requiere repetir el cobro real ya verificado.
