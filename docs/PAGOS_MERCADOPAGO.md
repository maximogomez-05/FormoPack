# Checkout Pro y acabado de interfaz

Incremento 2B, 26 de octubre de 2026. Implementación de Checkout Pro mediante
Preferences API y consulta de Payments API, conservando Python y reglas en clases.
No es una integración del producto QR presencial/Orders de Mercado Pago.

## Flujo y validaciones

`MercadoPagoService` encapsula el SDK, sus consultas y errores; no se accede al
SDK privado desde las rutas. `ConciliacionMP` crea órdenes locales y concilia
pagos. `PagoVerificadoMP` valida la respuesta consultada al proveedor.

Antes de abrir Checkout se exige personal activo, un turno propio abierto, envío
existente y ausencia de otro cobro. La orden conserva usuario, caja original,
importe, cuenta receptora y preferencia; su identificador va en metadata.
Volver a abrir el pago reutiliza el enlace guardado. Mientras se prepara uno,
otro inicio se rechaza; si falló la preparación, se permite reintentar después
de treinta segundos. Las llamadas al proveedor no retienen bloqueos SQL.

Para acreditar se consulta el ID concreto al proveedor y se comprueban:

- Identificador, estado aprobado y ausencia de importe reembolsado.
- Guía esperada, metadata y existencia de la orden local.
- Importe de la orden y costo vigente, moneda ARS y cuenta receptora.
- Modo de prueba/producción según la configuración de esta instalación.

Estos datos forman parte de la [respuesta de Payments API](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/get-payment/get).
Las órdenes nuevas permiten corroborar la procedencia; un pago pendiente de la
versión anterior sin metadata no se adopta automáticamente. Requiere revisión.

La escritura usa bloqueo del envío y lectura actual de pagos para idempotencia.
El índice único SQL de referencia externa impide reutilizar el mismo pago.
Un cobro distinto sobre un envío ya pagado se rechaza para revisión: no se
registra dos veces ni se realiza un reembolso automático.

La confirmación actualiza la modalidad del envío a digital en la misma
transacción. El comprobante de recepción existente sigue disponible.
No se anuncia aprobación antes de confirmar el guardado local.

## Webhook, polling y retorno

`FirmaMercadoPago` valida HMAC-SHA256, request-id, data.id y timestamp con tolerancia
de cinco minutos, siguiendo la [documentación oficial de notificaciones](https://www.mercadopago.com.ar/developers/en/docs/checkout-pro-preferences/payment-notifications)
y la [guía del SDK](https://github.com/mercadopago/sdk-nodejs/blob/master/docs/webhooks.md).
Se admiten timestamps en segundos y milisegundos; el reloj del servidor debe
estar sincronizado. La autenticación usa el identificador de la query y exige
que coincida con el cuerpo. No acepta IPN ni notificaciones de QR presencial.

Solo `/recepcion/mp/webhook` está exento de CSRF y de la sesión del personal;
exige su firma externa. Fallos de firma devuelven 401; de proveedor/persistencia,
503 para permitir reintentos. Una discrepancia definitiva de pago se acusa como
recibida con `revision=true`, sin acreditarlo; se registra advertencia para
diagnóstico. Los eventos no aprobados no generan cobros.

El polling pasa a POST con CSRF y rol de mostrador/administración. Consulta y
confirma mediante el mismo servicio, con límite de solicitudes. El retorno
GET del navegador muestra un mensaje neutral y nunca escribe ni acredita pagos
a partir de sus parámetros. El QR se genera en Python y se entrega como imagen;
no depende de una librería QR cargada desde CDN para mostrarse.

## Caja y transferencias manuales

Si la caja original sigue abierta, el pago se incorpora a ella tomando el
mismo bloqueo que el cierre. Si ya cerró, conserva `id_turno=NULL`: no cambia
su arqueo histórico. La orden mantiene el contexto de origen y administración
ve los últimos cien cobros externos sin turno en la pantalla de caja. La
asignación/conciliación posterior de esos ingresos no se automatiza aquí.

La opción de transferencia manual exige referencia del comprobante y una
confirmación expresa del operador de haber verificado la acreditación.
Mercado Pago no puede asentarse usando ese formulario ni un QR local inventado:
se utiliza su flujo de confirmación externa. Las otras billeteras/transferencias
siguen siendo registros manuales; no se afirma que sus APIs validen el dinero.

## Configuración y actualización

Con la aplicación detenida y respaldo comprobado:

```powershell
py -m app.core.migrations --desde 007
```

La migración agrega `ordenes_pago_mp` y el índice único de referencia externa
en `pagos`. El gestor rechaza referencias duplicadas antes de cambiar el esquema.
SQL reejecutable e inicializador completo comprobados en MariaDB 10.4.32.
No borra ni reasigna referencias históricas. Falta validación en el motor final
del hosting si se elige una versión diferente.

En `.env`, manteniendo los secretos fuera del repositorio:

```dotenv
MP_ACCESS_TOKEN=token_de_la_cuenta_de_prueba
MP_COLLECTOR_ID=identificador_del_vendedor
MP_WEBHOOK_SECRET=secreto_de_firma_de_la_integracion
MP_TEST_MODE=true
MP_BASE_URL=https://dominio-publico-de-pruebas
```

El webhook debe configurarse para notificaciones de pagos de Checkout Pro.
`MP_BASE_URL` determina los retornos y el webhook; localhost solo sirve para
desarrollo local y no recibe notificaciones externas sin una URL pública.
Reiniciar la aplicación tras actualizar estas variables. Antes de producción
se requieren credenciales coherentes, modo de producción y pruebas externas.

En esta sesión se verificó que falta cargar cuenta receptora y secreto de firma.
No se cambiaron ni expusieron las credenciales existentes. No pegar secretos en
el chat: se completan en el entorno local.

La migración 007 se aplicó a la base local después de restaurar y comparar los
conteos de las 19 tablas del respaldo:
`C:\Users\maxig\.codex\backups\formopack\pagos-20261026-001604.sql`.

## Ajuste visual

`refinamiento.css` conserva estructura, navegación y distribución. Cambia
contraste, sombras, bordes y colores de avisos/estados, usando superficies
neutras y acentos semánticos moderados. Añade transiciones breves, foco visible
y respeto por `prefers-reduced-motion`. Los avisos permanecen hasta cerrarlos
mediante su botón; no desaparecen mientras se lee una validación.

Si AOS no carga, se retiran sus atributos para que el contenido siga visible.
Se inspeccionaron capturas de escritorio (1440 px) y móvil (390 px), comprobando
que no hay desborde horizontal de página; las tablas conservan su scroll propio.

## Verificación y límites

Selección acumulada: 308 pruebas aprobadas y dos deseleccionadas. Incluye
regresión previa, tres recorridos Chrome (soporte, recepción y pago simulado),
idempotencia concurrente, fallos SQL, datos externos inconsistentes, firma,
modo de prueba, caja cerrada, migración repetida e índice SQL.
La instalación completa y su reejecución también se comprobaron en base aislada.

Ejecutar `tests/test_pagos_mp.py` con la instancia exclusiva definida en
`FORMOPACK_TEST_DB_PORT`. `tests/test_pagos_navegador.py` usa las variables
Node/Playwright descritas en [recepción](RECEPCION_VALIDACIONES.md) y admite
`FORMOPACK_PREVIEW_DIR` para conservar capturas. No ejecutar contra datos de trabajo.

El proveedor está simulado en las pruebas: aún se necesita una compra sandbox
externa con la cuenta del proyecto, acceso público HTTPS y notificación auténtica.
No se efectuaron cobros, reembolsos ni correos reales. Tampoco se certifica aún
el manejo contable de devoluciones/contracargos posteriores: no se revierten
pagos históricos automáticamente. Sigue pendiente una cola persistente de
notificaciones, supervisión de discrepancias y conciliación administrativa de
ingresos fuera de turno. Los límites por IP siguen en memoria hasta el despliegue.

## Diagramas

Agregar la orden local y sus relaciones en el DER, el índice de pago externo y
las clases de firma, validación y conciliación. Las secuencias deben reflejar
firma antes de consultar, retorno sin acreditación, validación del recurso,
bloqueo/idempotencia, commit antes de confirmar y caja cerrada sin alterar arqueo.
Los archivos gráficos permanecen para la etapa final.
