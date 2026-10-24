# Recepción, validaciones y caja

Incremento 2A, 24 de octubre de 2026. Alcance: RF 2.1–2.6 y manejo de errores
de entrada/persistencia, dentro de la revisión previa al despliegue.

## Reglas implementadas

`ValidacionEntrada` concentra las reglas reutilizables. `Cliente`, `Bulto`,
`SolicitudRecepcion`, los controladores y `Cotizador` las aplican en servidor.
Los controles HTML ayudan al usuario y no sustituyen esta validación.

| Dato | Regla |
| --- | --- |
| Nombre de cliente o personal | 3–100 caracteres, al menos dos letras; admite letras Unicode, espacios, puntos, apóstrofes y guiones; rechaza números, controles y textos solo de puntuación. Normaliza Unicode a NFC. |
| Documento de cliente | Conserva la regla existente de 7–15 dígitos ASCII, sin separadores. No comprueba identidad ni dígito verificador de CUIT. |
| Teléfono | 6–15 dígitos, hasta 20 caracteres con formato; + solo al comienzo, espacios y guiones permitidos, paréntesis equilibrados. |
| Correo | Opcional para clientes, obligatorio para personal; máximo 100 caracteres, formato sin espacios, punto inicial/final ni puntos consecutivos en la parte local. |
| Dirección | 3–200 caracteres, sin controles, con alguna letra de calle/barrio/referencia. No verifica existencia geográfica. |
| Identificadores | Enteros positivos representables por INT, sin booleanos, fracciones ni truncamiento. Localidad y seguro deben existir. |
| Bultos | 1–100 por solicitud; peso real entre 0,01 y 999.999,99 kg; volumétrico entre 0 y 999.999,99. Son límites de representación SQL, no habilitan sobrecarga del vehículo. |
| Importes | Finitos, no negativos, hasta 9.999.999.999,99 y como máximo dos decimales. Un cobro debe ser positivo y coincidir con el total del envío. |
| Seguro | Si se selecciona, exige valor declarado positivo. |

Los valores inválidos no se convierten silenciosamente en cero ni se redondean
para que entren en las columnas. Se rechazan NaN, infinito, booleanos, entradas
malformadas y tamaños fuera de rango. La fragilidad usa un booleano real en JSON
y el índice del bulto en formularios; desmarcar uno no desplaza las marcas restantes.

Antes de registrar clientes desde el alta de envío se valida el formulario
completo y se comprueban localidad, seguro y cotización. Un rechazo devuelve
HTTP 400 y conserva los valores, incluyendo los bultos. Esta revisión no convierte
la creación de clientes y envío en una única transacción: una falla posterior de
persistencia todavía puede dejar clientes válidos registrados sin su envío.

Se corrigió la URL de cotización en vivo en el alta de envío. Cuando el cálculo
es rechazado o falla, la interfaz informa el error y deja de presentar el
resultado anterior como si fuera la nueva cotización.

## Caja y cobros

`CajaController` bloquea la fila del usuario durante apertura y cierre y
comprueba cuenta activa y rol habilitado. Dos aperturas simultáneas del mismo
usuario no crean dos turnos a través de la aplicación. No se agregó un índice
de exclusividad para escrituras SQL externas.

El cierre exige el identificador del actor y titularidad de la caja, incluso
para administradores. Bloquea el turno, calcula totales y guarda estado,
ingresos y fecha de cierre en una transacción. Ante una falla se revierte todo.

`EnvioController.registrar_pago` valida importes y referencias, verifica el costo
vigente y, si se informa turno, exige su titular y estado abierto. Usa el mismo
bloqueo de turno que el cierre: un cobro concurrente queda incluido en el arqueo
o es rechazado si la caja ya cerró. El efectivo entregado se registra aparte
del precio del servicio y conserva el cálculo de vuelto.

Sigue pendiente completar la confirmación externa de Mercado Pago. Una referencia
QR local no demuestra acreditación bancaria. Tampoco se completan en este bloque
rendición del chofer, cuentas corrientes, retenciones documentales o conciliación
de pagos externos fuera de turno.

## Errores y verificación

Los errores de base no capturados por una ruta tienen respuesta controlada 503,
HTML o JSON según la petición, sin SQL ni trazas en pantalla. La cotización y la
búsqueda distinguen entradas inválidas de indisponibilidad. Los errores técnicos
se registran para diagnóstico. Las consultas de localidades, seguros y turno
ya no simulan listas vacías o ausencia de caja cuando falla la base.

Pruebas nuevas:

- `tests/test_validacion_recepcion.py`: nombres, contactos, caracteres de control,
  límites, decimales, listas y rechazo previo al acceso a la base.
- `tests/test_recepcion_bd.py`: alta completa, fragilidad, rechazo sin altas
  parciales por validación, errores SQL forzados, caja concurrente, titularidad,
  importes alterados, cierre/cobro simultáneos y rollback.
- `tests/test_recepcion_navegador.py` con `tests/browser/recepcion.cjs`: Chrome
  comprueba cotización en vivo, rechazo en servidor, conservación del formulario
  y posterior alta correcta sin duplicar el envío.

La selección acumulada aprobó 273 pruebas, con dos deseleccionadas. Usa la misma
instancia exclusiva y variables de ejecución descritas en [soporte](SOPORTE.md).
Incluye los recorridos existentes de soporte y permisos de páginas. No se
ejecutaron cobros ni correos reales, ni pruebas antiguas que alteran la base
de trabajo. Este bloque no necesita migración ni corrección automática de datos
históricos. No certifica que todos los módulos restantes estén terminados.

## Diagramas pendientes

Agregar las clases y operaciones de validación/solicitud de recepción; reflejar
validación antes de persistir, respuesta 400/503 y conservación del formulario;
incorporar bloqueos, titularidad y transacción de cierre/cobro. No cambia el DER
en este incremento y no se editaron archivos gráficos.
