# Plan de implementación de FormoPack Express

Fecha de inicio: 24 de octubre de 2026.

El objetivo es completar los 30 RF y los 7 RNF del documento académico,
mantener coherencia entre aplicación, esquema SQL, manual y diagramas, y
validar el sistema antes de su despliegue. El código actual es la base de
trabajo; una funcionalidad existente no se considera terminada hasta verificar
sus reglas, permisos, errores y persistencia.

## Forma de trabajo

Cada incremento debe resolver un conjunto acotado de problemas, incorporar
pruebas reproducibles, registrar sus límites y entregar las indicaciones para
actualizar los diagramas al finalizar las modificaciones de código. Sus
archivos gráficos quedan para la etapa final, según lo acordado con el equipo.

Python continúa siendo el lenguaje principal. Las reglas de negocio se
encapsulan en entidades y servicios, con controladores de aplicación y
repositorios responsables de la persistencia. HTML, CSS y JavaScript se
utilizan para presentación, APIs del navegador y PWA. La validación definitiva
pertenece al servidor. Los adaptadores de Flask no deben duplicar reglas del
dominio. La revisión hacia POO incluye retirar métodos vacíos y trasladar la
lógica y SQL de las rutas a clases con responsabilidades concretas.

No se ejecutan pruebas contra la base operativa, ni se envían correos o cobros
reales como parte de la suite. Las pruebas de integración deben utilizar una
base exclusiva y servicios de prueba. Las migraciones se versionan y validan
desde una instalación vacía y desde un esquema existente, con respaldo previo.

## Etapa 1 Seguridad y acceso

Requisitos: RF 1.1–1.3, RF 5.6 y RNF 3.1 y 4.1.

### Incremento 1A Implementado y probado de forma aislada

- [x] No devolver el OTP desde el controlador ni mostrarlo en pantalla,
  incluida una instalación sin SMTP.
- [x] Misma respuesta HTTP y mensaje de solicitud para una cuenta activa,
  inexistente o inactiva. Esto no certifica igualdad de tiempos de respuesta.
- [x] Entidad `RecuperacionContrasena`: generación criptográfica de seis dígitos
  ASCII, vigencia de quince minutos, validación y consumo único.
- [x] Usar la hora de MySQL para emisión y validación del vencimiento.
- [x] Bloquear el usuario y el código durante su consumo; guardar el cambio
  de contraseña e invalidación en la misma transacción con rollback ante error.
- [x] Sustituir las pruebas de recuperación que modificaban usuarios reales
  por pruebas aisladas del modelo y controlador.
- [x] Manejar CSRF mediante una clase: HTTP 400, respuesta JSON para APIs,
  sin redirección a un Referer externo ni respuesta final 200 que simule éxito.
- [x] Conservar HTTP 429 para límites de solicitudes, con respuesta HTML/JSON.

No requiere migrar el esquema. Los bloqueos se implementaron con `FOR UPDATE`;
su comportamiento concurrente aún debe probarse en MySQL/InnoDB real de pruebas.
No certifica la entrega SMTP, que conserva la implementación asíncrona existente.

### Incremento 1B Recuperación y sesiones implementado y probado

- [x] Persistir HMAC-SHA256 del OTP ligado al usuario; migración 005
  reejecutable que borra e invalida los códigos anteriores en claro.
- [x] Limitar emisiones a cinco por cuenta y hora, separadas por un minuto,
  y a cinco verificaciones incorrectas por OTP, con persistencia compartida.
- [x] Revocar sesiones tras desactivar usuarios y restablecer contraseñas;
  renovar el identificador al autenticar y devolver 403 para permisos insuficientes.
- [x] Unificar el hash de contraseñas y validar el máximo de 72 bytes UTF-8.
- [x] Evitar que reinicializar los scripts reemplace contraseñas existentes.
- [x] Probar límites y consumo concurrente en MariaDB 10.4/InnoDB aislado.

Resultado acumulado: 130 pruebas aprobadas, incluidas diez de integración
con base real desechable y pruebas simultáneas. La migración 005 se aplicó a
la base local después de generar, restaurar y comprobar un respaldo en una
instancia aislada. Ver [actualización de seguridad](SEGURIDAD_ACCESO.md).

### Incremento 1C Soporte exclusivo implementado y probado

- [x] Encapsular permisos y validación en `ChatSoporte` y `MensajeSoporte`,
  con transacciones coordinadas por `SoporteController` y rutas de presentación.
- [x] Garantizar un operador por chat y un chat activo por operador, con bloqueos
  y una restricción única en la base. Probar ambas carreras concurrentes.
- [x] Responder únicamente como operador asignado; permitir supervisión y
  cierre administrativo, sin suplantar al responsable de la conversación.
- [x] Conservar el registro de atención cerrado y purgar sus mensajes en una
  sola transacción, conforme a RF 5.6 y su descripción de secuencia.
- [x] Ligar el chat público a la sesión del servidor; eliminar el token de
  URLs, respuestas y almacenamiento JavaScript. Proteger todos los POST con CSRF.
- [x] Validar entradas, limitar solicitudes públicas y conservar el texto
  redactado cuando falla el envío. Acceder al soporte sin una guía previa.
- [x] Retirar la creación de tablas del controlador y versionar el esquema en 006.

Validación acumulada de esta selección: **173 pruebas aprobadas y dos
deseleccionadas**, incluidas integración y concurrencia en MariaDB 10.4 y un
flujo completo en Chrome. No representa la aceptación de todos los RF.
La migración 006 se aplicó a la base local tras restaurar y cotejar las 19 tablas
de un respaldo aislado. Detalles y cambios para los diagramas: [soporte](SOPORTE.md).

### Pendientes de seguridad

Incremento de primer acceso: las cuentas nuevas reciben clave provisoria y
deben reemplazarla antes de operar; la restricción se comprueba en servidor.
Cambio atómico con revocación de sesiones y recuperación OTP coherente.
Se agrega Inicio en tracking/paneles y una vista compacta de actividad con
opción de período completo. Ver [detalle y migración 008](PRIMER_ACCESO_Y_NAVEGACION.md).
Validación acumulada de la selección aislada: 329 pruebas aprobadas y dos
deseleccionadas, con recorridos Chrome de alta, cambio obligatorio y navegación.

- [ ] Evaluar diferencias temporales de recuperación y compartir el límite
  por IP entre procesos; programar limpieza de registros sin actividad.
- [ ] Aplicar las excepciones CSRF solamente a endpoints que lo necesiten.
- [ ] Revisar acceso a evidencias, límites de entradas públicas y datos expuestos.

Cierre de etapa: pruebas de autorización, recuperación, sesiones y chat con
casos positivos, negativos y concurrencia; sin filtración de secretos.

## Etapa 2 Pagos, recepción y caja

Requisitos: RF 2.1–2.8, 5.2 y 6.3.

### Incremento 2A Validación de recepción y caja

Implementado: validadores de texto, contactos, identificadores y decimales;
validación completa del formulario antes de crear clientes; límites alineados
con el esquema; fragilidad por índice de bulto; cotización en vivo corregida;
formularios conservados tras un rechazo; errores de persistencia controlados.
La apertura de caja se serializa por usuario; el cierre exige titularidad y
guarda su conciliación en una transacción. El cobro comprueba total exacto,
turno propio abierto y bloqueo compartido con el cierre.

Validación: 273 pruebas acumuladas en la selección aislada, dos deseleccionadas.
Incluye Chrome para recepción y soporte, recorrido HTTP de caja/cobro/comprobante,
entradas inválidas, concurrencia y fallos SQL forzados. No exige migración nueva
ni modifica los datos operativos. Detalles: [recepción y validaciones](RECEPCION_VALIDACIONES.md).

La acreditación externa de Mercado Pago, rendiciones en destino e inmutabilidad
documental siguen pendientes. Este incremento no cierra toda la etapa 2.

### Incremento 2B Checkout Pro y acabado visual

Implementados el contexto de orden local, validación de firma y recurso externo,
idempotencia SQL, polling POST con CSRF y retorno sin acreditación por querystring.
El checkout reutiliza la preferencia guardada y el QR se genera en Python.
La transferencia manual queda separada. Los ingresos recibidos tras el cierre
se conservan fuera de turno y son visibles para administración.

Se refinan contrastes, avisos y bordes sin cambiar la distribución, con
transiciones discretas y respeto por movimiento reducido. Ver
[configuración, pruebas y límites](PAGOS_MERCADOPAGO.md).

La selección acumulada comprende 308 pruebas. Falta completar cuenta receptora
y secreto de webhook en el entorno y verificar una compra sandbox auténtica;
las pruebas automatizadas simulan el proveedor y no realizan cobros reales.

- [x] Encapsular la confirmación de Mercado Pago en un servicio: comprobar
  estado, referencia, importe, moneda y destinatario comercial del pago.
- [x] Autenticar notificaciones de Checkout Pro/Preferences mediante firma;
  eximir de CSRF el webhook específico y gestionar reintentos reales.
- [x] Unicidad del pago externo e idempotencia de webhook y polling; retorno de
  navegador sin escritura de pagos.
- [x] No anunciar aprobación si falla la conciliación local.
- [x] Conservar contexto de caja original y registrar fuera de turno si ya cerró.
- [ ] Completar conciliación administrativa posterior de esos ingresos,
  devoluciones/contracargos y una prueba externa con la cuenta de sandbox.
- [x] Validar titularidad y estado del turno, serializar apertura y cierre y
  coordinar el registro de cobros con el cierre en la aplicación.
- [ ] Separar pago acreditado, registro manual de transferencia, cuenta corriente
  y cobro en destino; completar rendición del chofer, saldos y diferencias.
- [x] Corregir el índice de los checkboxes de fragilidad en multibulto.
- [ ] Validar dimensiones, pesos e importes finitos y positivos en servidor;
  calcular el aforo allí y unificar divisor, descuentos, mínimos y redondeos.
- [ ] Mantener una copia histórica de los datos de cada documento emitido,
  incluyendo desglose económico, fecha y operador, con exportación completa.

Cierre de etapa: no duplicar cobros, no asociarlos a otro envío, no operar
cajas ajenas ni perder movimientos de conciliación. Pruebas con entorno de
Mercado Pago de prueba, desconexiones y notificaciones repetidas.

## Etapa 3 Estados, inventario y logística

Requisitos: RF 3.1–3.5, 4.5, 5.5 y 6.1.

Incremento 3A: despacho y visitas con historial independiente, reserva/inicio,
restricciones SQL, reintentos y cierre operativo implementados. Ver
[reglas, migración y límites](LOGISTICA_ESTADOS.md). El cierre distingue visita
resuelta de encomienda finalizada; RF 6.1 requiere ajustar esa precisión.
Retiro físico, seguro y endurecimiento de evidencias todavía están pendientes.

- [x] Centralizar en una clase las transiciones de envío y sus precondiciones;
  aplicar las mismas reglas desde chofer, recepción y administración.
- [ ] Registrar actor, momento y motivo; impedir entrega sin evidencia requerida.
- [x] Unificar disponibilidad en depósito y criterios de selección de despacho.
- [x] Impedir asignar el mismo envío o recurso a despachos incompatibles,
  incluso ante solicitudes simultáneas.
- [ ] Definir reintento, custodia al tercer fallo, retiro en sucursal y devolución;
  impedir nuevos intentos domiciliarios al alcanzar el límite.
- [ ] Cierre automático coherente desde todos los recorridos de actualización,
  con liberación de vehículo y disponibilidad del chofer.
- [ ] Completar mantenimiento y gestión de flota según el alcance definitivo.
- [ ] Validar capacidad por peso y resolver la promesa documental de volumen:
  si se conserva, incorporar sus datos y controles explícitos.
- [ ] Mantener ruteo por corredores/kilometraje del RF 3.3, documentando su
  alcance real, y evitar describirlo como optimización vial no implementada.
- [ ] Completar siniestros, bloqueo de entrega y gestión de seguro.

Cierre de etapa: ciclo completo y excepciones coherentes, sin envíos
desasignados accidentalmente ni recursos bloqueados al terminar el trabajo.

## Etapa 4 Entregas, tracking y operación offline

Requisitos: RF 4.1–4.4, 5.1, 5.3–5.4 y 6.2; RNF 2.1.

- [ ] Validar DNI, firma con contenido, imágenes y coordenadas en servidor.
- [ ] Implementar comprobante PDF de entrega con evidencia y credencial de
  retiro coherentes con la documentación y sus permisos de descarga.
- [ ] Aplicar la política de privacidad del tracking y resolver la consulta
  por DNI del RF 5.1 con protección de datos personales.
- [ ] Identidad de operación offline e idempotencia persistente en servidor.
- [ ] Aislar caché y cola por usuario; gestionar logout y cambio de cuenta.
- [ ] Distinguir validación rechazada, sesión/CSRF vencido, error de servidor
  y falta de red; mostrar al chofer qué quedó guardado y qué fue confirmado.
- [ ] Completar iconos y verificar instalación de la PWA.
- [ ] Probar GPS, permisos, pérdida de señal y suspensión del navegador en móviles.
- [ ] Enlaces de correo con URL pública y guía; envío persistente con reintentos.
- [ ] Completar indicadores mensuales/SLA y separar facturación de recaudación.

Cierre de etapa: una entrega registrada sin señal se confirma una sola vez
al reconectar; no desaparece ni se mezcla con datos de otra cuenta. Validación
con teléfonos reales, incluida aplicación suspendida y navegador reiniciado.

## Etapa 5 Trazabilidad académica y documentación

Requisitos: todos los RF y RNF 4.1.

- [ ] Matriz individual de los 30 RF: criterio de aceptación, clase/endpoint,
  prueba, estado y referencia al diagrama/manual.
- [ ] Unificar alcance provincial, estados, nomenclaturas, factor de aforo,
  numeración de requisitos y versiones de documentos.
- [ ] DER comparado con migraciones y esquema real, incluyendo opcionalidad,
  claves únicas, cardinalidades e índices.
- [ ] Diagrama de clases con clases, atributos y operaciones existentes.
- [ ] Casos de uso con actores, permisos y relaciones UML correctos.
- [ ] Secuencias con orden real de persistencia, cobro, despacho y excepciones.
- [ ] Manual actualizado con recorridos comprobados y datos de ejemplo
  identificables, sin credenciales ni garantías no verificadas.

La alineación se revisa en cada incremento; esta etapa consolida la versión
para evaluación. Un diagrama no sustituye una funcionalidad exigida por un RF.

## Etapa 6 Despliegue y aceptación

Requisitos: RNF 1.1–1.2, 2.2, 3.1–3.2 y 4.1.

- [x] Elegir proveedor: Hostinger VPS, indicado por el usuario.
- [ ] Contratar y dimensionar el VPS; configurar persistencia, MySQL y separación
  entre pruebas y producción. La infraestructura todavía no está provisionada.
- [ ] Desactivar debug; servidor WSGI, HTTPS, secretos y usuario SQL con
  privilegios mínimos. Evitar DDL y usuarios semilla durante el arranque web.
- [ ] Unificar migraciones compatibles con la versión del motor elegido;
  no restablecer contraseñas de demostración al actualizar.
- [ ] Persistencia compartida de sesiones, límites y evidencias según el despliegue.
- [ ] Backups diarios de base y evidencias, restauración comprobada y rollback.
- [ ] Monitoreo, registros y alertas; medir disponibilidad para el objetivo 99,9 %.
- [ ] Medir PDFs en menos de tres segundos con cargas representativas y
  realizar pruebas concurrentes de la operación de varias sucursales.
- [ ] Aceptación integral: recepción → cobro → despacho → entrega/fallo →
  tracking → comprobante → caja/rendición, incluida pérdida de conectividad.

## Diagramas

La edición de clases, DER, casos de uso y secuencias se realizará al terminar
las modificaciones de código. Se conserva la lista de cambios implementados
para preparar entonces las instrucciones o scripts de draw.io completos.

## Validación del incremento 1A

Las pruebas de recuperación y HTTP se ejecutan sin MySQL y con correo simulado:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -B -m pytest -q -p no:cacheprovider tests/test_recuperacion_password.py tests/test_seguridad_http.py
```

Resultado de este incremento: 46 pruebas específicas aprobadas. Al sumar la
selección segura de regresión de cotizador, modelos, tracking, notificaciones,
liquidaciones y autenticación: **98 aprobadas y 2 deseleccionadas**. No es la
suite completa ni una prueba de concurrencia contra un motor real.

Referencia de seguridad: [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

El webhook de Checkout Pro usa firma externa y una exención CSRF específica
desde el incremento 2B. La compra sandbox externa sigue pendiente de configuración.
La suite completa conserva pruebas antiguas que necesitan aislarse antes de
ejecutarlas; no debe apuntarse automáticamente a la base de trabajo.
