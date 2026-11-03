# Privacidad de documentos y evidencias

Incremento del 3 de noviembre de 2026. La comprobación de un pago nuevo de
Mercado Pago queda pendiente y no forma parte de este incremento.

## Accesos

| Recurso | Público | Chofer | Recepción / Administración |
| --- | --- | --- | --- |
| Seguimiento por guía | Estado, fechas, localidad e iniciales | Vista pública | Vista pública |
| GPS del reparto activo | Se conserva durante `en_ruta` | Se conserva durante `en_ruta` | Se conserva durante `en_ruta` |
| Constancia pública de entrega | Estado y localidad, sin firma, nombres completos, domicilio ni importe | Igual | Igual |
| Credencial pública de retiro | Guía e instrucciones cuando ingresó físicamente a central | Igual | Igual |
| Comprobante interno, PDF, remitos y etiqueta | Sin acceso | Sin acceso | Permitido |
| Fotos y firmas de entrega | Sin acceso | Sin acceso de descarga | Permitido desde el comprobante interno |
| Constancia firmada de devolución al remitente | Sin acceso | Sin acceso | Permitido |

El chofer conserva las funciones de captura de firma y foto de su visita.
La consulta del documento financiero completo no es necesaria para esas funciones.
El retiro en mostrador mantiene la validación del DNI del remitente registrado;
la interfaz no ofrece un retiro por terceros que el servicio no implementa.

El seguimiento público no recibe domicilio, importe ni datos completos de las
partes en su contexto de plantilla. Las ubicaciones y observaciones libres del
historial se convierten en ubicaciones generales y motivos tipificados. No se
publican las coordenadas del domicilio tomadas al finalizar un intento. El
mapa referencial conserva la localidad y el GPS activo previsto por RF 5.1.
El formulario de soporte solicita el nombre a quien consulta, sin autocompletar
el nombre del destinatario a partir de una guía pública.

## Archivos

`AlmacenEvidencias` guarda fotografías nuevas en `instance/private/pod`, con
permisos 700 para la carpeta nueva y 600 para el archivo en Linux. Se conserva
la clave lógica `uploads/pod/<nombre>` en la base para no cambiar el protocolo
offline ni requerir migración SQL. Las fotos anteriores pueden permanecer en
`web/static/uploads/pod`, pero Flask rechaza todas las solicitudes de archivos
de `uploads` por la ruta estática, incluso con sesión iniciada. No se mueven ni
se eliminan archivos históricos durante una petición.

Las descargas usan `/documentos/evidencias/<id_intento>/foto` o `/firma` y
requieren sesión vigente de recepción o administración. Resuelven el archivo
desde el registro SQL, sin aceptar una ruta de archivo proporcionada por el
cliente. Se rechazan rutas fuera de las carpetas permitidas, incluidas rutas
resueltas por enlaces simbólicos. Las firmas admitidas se recodifican como PNG;
datos inválidos o SVG no se sirven como contenido activo.

Las respuestas privadas no se almacenan en caché y se entregan como descargas,
sin ETag ni respuestas condicionales 304. El service worker conserva únicamente
el panel del chofer y los recursos estáticos de su lista permitida; no incorpora
evidencias ni documentos descargados. Se añade `Referrer-Policy: same-origin`
para evitar enviar la URL de seguimiento a recursos de otro origen.

## Despliegue y respaldos

No requiere migración SQL. La configuración de Nginx vigente reenvía las
peticiones a Flask. Si en el futuro Nginx sirve directamente los archivos de
la aplicación mediante `alias` o `root`, debe conservarse una denegación
explícita para `/static/uploads/`; no debe publicarse `instance/private`.

El respaldo diario del VPS debe actualizarse junto con el código: el script
anterior solo incluía `.env` y las fotos antiguas. La versión del repositorio
incluye también `instance/private`. Conserva destino protegido, bloqueo de
ejecución simultánea, volcado SQL, revisión Git, verificación de gzip y retención
de catorce días. La prueba local ejecuta el script en raíces temporales, con
SQL y revisión simulados, y abre el archivo final para comprobar ambos tipos
de fotos. El respaldo contiene secretos y datos personales y debe mantenerse
con acceso restringido.

En el VPS, ejecutar una línea por vez y detenerse ante cualquier error:

```bash
cd ~/formopack-app
sudo /usr/local/sbin/formopack-backup
git pull --ff-only
sudo install -m 700 scripts/vps/formopack-backup /usr/local/sbin/formopack-backup
sudo /usr/local/sbin/formopack-backup
sudo systemctl restart formopack
systemctl is-active formopack
```

Las copias descargadas antes de este incremento conservan su contenido original.
La siguiente copia externa debe obtenerse de un respaldo generado con el script
nuevo para conservar también las evidencias privadas futuras.

## Validación y documentación académica

Las pruebas usan un motor SQL desechable y no envían correos ni crean cobros.
Cubren permisos por rol, sesiones revocadas, archivos nuevos e históricos,
subida y reintento idempotente, limpieza ante rechazo, nombres/rutas manipulados,
descarga de firma y foto, PDFs internos, minimización del seguimiento y respaldo.
Se revisan también entrega, devolución y firma en mostrador desde Chrome.
Resultado: 109 pruebas aprobadas y una omitida por permisos del sistema.
La comprobación real de enlaces simbólicos se omite en Windows cuando el sistema
no concede permisos para crearlos; debe comprobarse también en Linux.

El DER no cambia por este incremento. En clases y secuencias incorporar
almacenamiento privado, sesión/rol antes de descargar y la vista pública mínima.
Revisar RNF de confidencialidad y manual: la guía por sí sola permite consultar
el estado, pero no descargar evidencias ni el comprobante financiero completo.
