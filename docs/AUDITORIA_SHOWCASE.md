# Auditoría de funcionamiento y preparación del showcase

Fecha: 12 de noviembre de 2026. Base revisada: `4b39981` de `main`, coincidente con `origin/main` al comenzar. Las correcciones de esta auditoría están en el commit que incorpora este archivo.

## Alcance y entorno

Windows, Python 3.13.3, MariaDB local desechable en el puerto 33317 y Chrome automatizado con Playwright. Cada prueba de integración crea y elimina su propia base aleatoria. Se verificó la compatibilidad de dependencias con `pip check`. No se desplegó en el VPS, no se usó la base publicada ni se enviaron correos, cobros o devoluciones reales.

Las respuestas de Mercado Pago, SMTP, geocodificación y ruteo se simularon. Las pruebas de navegador interceptan proveedores externos. La nueva protección automática de pytest bloquea SMTP y solicitudes externas de Python para evitar que una prueba alcance servicios reales accidentalmente.

## Defectos reproducidos y correcciones

| Prioridad | Escenario observado | Corrección y evidencia |
|---|---|---|
| Alta, bloquea demostración | Un alta válida en mostrador devolvía 503: el cursor entregaba una tupla de localidad y el código intentaba leerla como diccionario. | Lectura consistente con el cursor. Regresión contra MariaDB y recorrido real del formulario en Chrome, conservando rechazo de entradas inválidas e idempotencia. |
| Media | La preparación de ejemplos fallaba por la misma confusión de tuplas; además descartaba las coordenadas al insertar el envío. | Se utiliza el centro de la localidad y se guardan las coordenadas. Se comprueban los 14 ejemplos nuevos, repetición sin duplicados y rollback ante conflicto. Son ubicaciones ficticias de demostración. |
| Media | Sin Leaflet, un error JavaScript interrumpía el formulario de recepción y el seguimiento público. | El formulario mantiene autocompletado por DNI y validación firmada de dirección mediante sugerencias; el tracking mantiene sus consultas de estado y explica la ausencia de mapa. Chrome ensaya explícitamente el CDN ausente. |
| Media | Respuestas malformadas de geocodificación podían provocar errores; coordenadas NaN no se rechazaban en la comparación con la sugerencia firmada. | Se rechazan coordenadas no finitas y fuera de rango; se filtran elementos malformados. Casos adversariales específicos. |
| Media | Una matriz de ruteo incompleta o con valores inválidos podía llegar al solver nativo. | Se valida dimensión, filas y valores de ambas matrices. Ante datos inválidos se utiliza la estimación geográfica identificada como aproximada. Pruebas de matrices negativas, incompletas, texto, booleanos, NaN e infinito. |

Se actualizaron pruebas que todavía usaban el nombre anterior del botón de despacho o una respuesta de tracking sin historial GPS. El ensayo offline ahora espera la coincidencia entre cookie del worker y panel guardado antes de cortar la red; mantiene las comprobaciones de aislamiento entre dos choferes. No se relajaron requisitos de dirección, permisos ni validación de pagos.

## Cobertura de la regresión

Se ejecutan pruebas de campos y límites, cotización, efectivo y vuelto, pago digital simulado e idempotencia, alta concurrente, reserva de chofer y vehículo, capacidad, resolución de visitas, tercer fallo, recepción física y retiro en central, cancelación, soporte exclusivo, perfiles propios, fotos, OTP, sesión única y expiración, CSRF, privacidad de documentos, rollback y fallos de infraestructura.

Chrome cubre recepción en tamaños de escritorio y móvil emulado, despacho e inicio de ruta, entrega con firma, reintento offline, dos choferes en un dispositivo, retiro, checkout simulado, soporte, perfil, primer acceso, sesiones y mapas con señales antiguas, fallos de consulta y respuestas externas inválidas.

Resultado final del conjunto completo: **642 aprobadas, 0 fallidas y 1 omitida**, en 326,41 segundos, con MariaDB y Chrome habilitados. Comando: `py -m pytest -q --disable-warnings --tb=short -r a`, con las variables `FORMOPACK_TEST_DB_PORT`, `FORMOPACK_TEST_NODE`, `FORMOPACK_TEST_PLAYWRIGHT`, `FORMOPACK_TEST_CHROME` y `FORMOPACK_TEST_LEAFLET` apuntando al entorno desechable descrito arriba.

La omitida es `test_almacen_rechaza_enlace_simbolico_fuera_de_la_carpeta`: Windows rechazó la creación del enlace antes de poder ensayar la aplicación. Hubo cuatro avisos de deprecación de dependencias (SWIG y ReportLab); no fueron fallos de funcionamiento. También pasaron `pip check`, compilación de Python, comprobación de sintaxis de los scripts de navegador modificados y `git diff --check`.

Antes de esta pasada se reprodujeron los defectos indicados y se hicieron regresiones dirigidas: 40 casos nuevos de proveedores, recepción/caja (26 casos) y un conjunto de 11 pruebas de navegador/PWA. La última ejecución completa incluye estas verificaciones sobre el código corregido.

## Pendientes y veredicto

**Listo con limitaciones para un showcase controlado, después de aplicar estas correcciones y hacer un ensayo en el VPS.** La aprobación se limita a los recorridos automatizados y al entorno indicado; no acredita ausencia total de bugs ni equivalencia completa entre Windows y el servidor Linux.

Indispensable antes de presentar:

1. Respaldar, actualizar el VPS y comprobar inicio de sesión, nuevo envío con dirección validada y consulta de seguimiento. Esta auditoría no ejecutó ese despliegue.
2. Ensayar con las cuentas que se mostrarán; preparar remitente, destinatario, vehículo y chofer de demostración. No confundir ejemplos con operaciones reales ni repetir cobros para rellenar métricas.
3. Si se anunciará GPS u operación offline en teléfono físico, comprobar permisos, pérdida de conexión, suspensión y reapertura en ese teléfono. La emulación de Chrome no sustituye esa aceptación.
4. Si se anunciará conciliación automática de un nuevo pago real, completar ese ensayo cuando haya otra cuenta disponible. El pago previo de $500 es evidencia histórica aportada por el usuario; no se repitió aquí.

Validaciones externas pendientes: restauración de una copia externa reciente en Linux, accesos mediante enlaces simbólicos donde Windows no permite crearlos, servicios y certificado del VPS y disponibilidad real de proveedores. No bloquean una demostración local controlada, pero sí afirmar que todo el entorno productivo quedó certificado.

Mejoras opcionales: ajustes visuales puntuales y medición de carga con concurrencia representativa. No se propone ampliar funciones ni rehacer el dashboard durante este cierre.

La corrección de ejemplos guarda coordenadas en los ejemplos nuevos; no reescribe los ya existentes. Si un ejemplo anterior carece de ubicación, no será elegible para optimización hasta resolver sus datos por un procedimiento controlado. Para el guion se recomienda registrar un envío nuevo con dirección validada.

## Guion breve de demostración

1. Ingresar como administrador; explicar cobrado frente a tarifado y actividad frente a situación actual.
2. Abrir caja, recuperar cliente por DNI y registrar un envío con dirección validada; mostrar un rechazo de campo y corregirlo.
3. Cobrar en efectivo mostrando importe recibido y vuelto; descargar comprobante interno y etiqueta. Aclarar que no son factura fiscal.
4. Asignar chofer y vehículo; mostrar capacidad y propuesta de ruta como planificación, diferenciada del recorrido GPS.
5. Iniciar la hoja como chofer y registrar entrega con DNI y firma; verificar cierre automático y constancia pública sin datos sensibles.
6. En otro envío preparado, mostrar fallo, retorno, recepción física en central y retiro por remitente, como pasos separados.
7. Mostrar perfil propio, soporte y recuperación de errores. Para Mercado Pago usar una prueba simulada identificada o la evidencia del cobro ya realizado; no simular un éxito productivo.

## Aplicación de esta corrección al VPS (no ejecutada)

No agrega dependencias ni migraciones. Desde PowerShell:

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\formopack_hostinger" formopack@179.197.72.194
```

Dentro de la sesión SSH:

```bash
cd ~/formopack-app &&
sudo /usr/local/sbin/formopack-backup &&
git pull --ff-only &&
.venv/bin/python -m pip check &&
sudo systemctl restart formopack
systemctl is-active formopack
curl --fail --retry 5 --retry-delay 2 --retry-all-errors -sS -o /dev/null -w 'HTTP %{http_code}\n' https://formopackexpress.tech/
git log -1 --oneline
```

Se espera `active` y `HTTP 200`. Si un paso falla, revisar su salida antes de continuar. Abrir los formularios nuevamente para obtener sesiones y tokens actuales. No ejecutar cargas de ejemplos ni pytest contra la base publicada como parte de estos comandos.
