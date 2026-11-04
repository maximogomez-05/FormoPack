# Cierre técnico del 3 de noviembre

## Resultados

El gestor de conexiones publica la instancia únicamente cuando el pool terminó de inicializarse. Una caída al arrancar permite reintentar en la siguiente petición. Si el conector rechaza un commit, el contexto intenta rollback, libera la conexión y propaga el error.

El tracking diferencia una guía inexistente de una caída de MariaDB. Un fallo de lectura devuelve 503 con un mensaje público. El tracking ya no consulta las coordenadas privadas de intentos finalizados. Las consultas de comprobantes, choferes, envíos, alertas y liquidaciones propagan sus fallos al manejador de errores. Los CSV administrativos conservan los importes numéricos y protegen las celdas de texto que una hoja de cálculo podría evaluar como fórmulas.

En el VPS los límites de peticiones pueden usar la IP que escribe Nginx en X-Real-IP. Requiere activar FORMOPACK_PROXY_LOCAL=1, Gunicorn accesible únicamente desde loopback y Nginx sobrescribiendo la cabecera con la dirección del cliente. El cliente externo no determina la IP enviando X-Forwarded-For. El contador sigue en memoria del worker. Se reinicia al reiniciar el servicio y cada worker tendría un contador independiente. Antes de aumentar la cantidad de workers, configurar y verificar un almacén compartido.

## Despliegue

Desde la sesión SSH del usuario formopack, ejecutar una línea por vez. El grep debe mostrar la directiva del sitio y ss debe mostrar Gunicorn en 127.0.0.1:8000. Si la topología difiere, dejar desactivado el modo de proxy hasta revisarla.

```bash
cd ~/formopack-app
sudo /usr/local/sbin/formopack-backup
git pull --ff-only
sudo grep -F 'proxy_set_header X-Real-IP $remote_addr;' /etc/nginx/sites-enabled/formopack
ss -lnt 'sport = :8000'
.venv/bin/python -c "from dotenv import set_key; set_key('.env','FORMOPACK_PROXY_LOCAL','1')"
sudo systemctl restart formopack
systemctl is-active formopack
curl -sS -o /dev/null -w '%{http_code}\n' https://formopackexpress.tech/
```

No se requiere migración SQL. El resultado esperado es servicio activo y HTTP 200. Abrir el panel, consultar una guía y descargar un reporte con una cuenta autorizada. Conservar una copia externa reciente del respaldo.

## Verificaciones y pendientes

Se verificaron transacciones fallidas, reintento del pool, límites de login por IP, entradas de texto al CSV, tracking y respuestas ante errores SQL. Las pruebas de MariaDB usaron bases temporales exclusivas. Se verificaron los recorridos de recepción, pago simulado, despacho y devolución en Chrome.

Para el ensayo académico, recorrer mostrador → caja → ruta → entrega → comprobante y un caso de retorno al remitente. Para cerrar la aceptación externa quedan la confirmación automática de un nuevo QR real, una jornada offline en teléfono físico incluyendo suspensión y reapertura, la prueba de enlaces simbólicos en Linux y la restauración aislada de una copia externa reciente que incluya evidencias privadas. La revisión académica de requisitos, manual y diagramas corresponde a la etapa final.

## Verificación operativa del 4 de noviembre

Al reenviar el alta, el mostrador generaba dos guías. La migración 014 identifica cada formulario por operador. La creación de clientes, envío, bultos, historial, comprobante y asociación a la solicitud comparte una transacción. Al recibir dos solicitudes iguales se abre la misma guía. Para registrar otra encomienda se abre un formulario nuevo. Un formulario anterior al despliegue pide revisar y confirmar los datos una vez más.

En el panel del chofer, las visitas rechazadas indican el motivo y admiten reintento manual. Una visita que requiere revisión permite transmitir las siguientes. Ante pérdida de conexión, sesión vencida o fallo temporal de servidor, el dispositivo conserva la operación y su evidencia. Para una sesión vencida se debe reabrir el panel con la misma cuenta. En equipos con la primera versión del almacenamiento local se conserva el almacén al actualizar. Los registros antiguos que no identifican al chofer solo son visibles si conservan el token de su sesión original.

Las verificaciones se realizaron contra MariaDB local desechable, con cuentas y evidencias de prueba. Cubrieron mostrador y caja, cobros y notificaciones simulados, despacho y capacidad, entrega y devolución al remitente, permisos, documentos y sesiones. Chrome recorrió recepción a 390, 820 y 1440 píxeles, primer ingreso, historial, checkout, firma y retiro en central. En el dispositivo emulado se comprobó la reapertura offline y el aislamiento entre dos choferes. Se reprodujeron y corrigieron la duplicación del alta y el aborto de actualización de IndexedDB. Dos verificaciones de navegador dependían de nombres de controles anteriores al rediseño y una esperaba la versión de sesión anterior al ingreso único.

**Aplicación en el VPS.** Hacer respaldo, actualizar el código y aplicar con la cuenta administrativa local de MariaDB antes de reiniciar el servicio.

```bash
cd ~/formopack-app &&
sudo /usr/local/sbin/formopack-backup &&
git pull --ff-only &&
sudo mariadb formopack_db < scripts/migrations/014_solicitudes_mostrador.sql &&
sudo systemctl restart formopack &&
systemctl is-active formopack
```

El ensayo de enlaces simbólicos se omitió en Windows por permisos. Quedan para aceptación en el entorno correspondiente la restauración de una copia externa que incluya evidencias, el ensayo en Linux de enlaces simbólicos, la suspensión y reapertura en teléfono físico, y un nuevo QR real con conciliación automática. La cuenta de ejecución de la aplicación conserva sus permisos habituales.
