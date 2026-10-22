# 📦 Informe de Nuevas Funcionalidades, Mejoras y Correcciones del Sistema
## FormoPack Express — Plataforma de Gestión Logística y Envíos

> **Fecha:** 21 de Octubre de 2026  
> **Área:** Funcionalidades Operativas, Experiencia del Cliente y Gestión Administrativa  
> **Estado:** ✅ Implementado, probado y validado (92 tests superados al 100%)  

---

## 📑 Índice de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Portal de Tracking Público Enriquecido (Experiencia del Cliente)](#2-portal-de-tracking-público-enriquecido)
3. [Módulo de Soporte al Cliente y Atención en Tiempo Real](#3-módulo-de-soporte-al-cliente-y-atención-en-tiempo-real)
4. [Recuperación Segura de Contraseñas por Correo](#4-recuperación-segura-de-contraseñas-por-correo)
5. [Corrección Integral del Dashboard y Gestión de Pedidos](#5-corrección-integral-del-dashboard-y-gestión-de-pedidos)
6. [Corrección de Navegación, Roles y Redirecciones](#6-corrección-de-navegación-roles-y-redirecciones)
7. [Batería de Pruebas y Validación](#7-batería-de-pruebas-y-validación)

---

## 1. Resumen Ejecutivo

En esta etapa de desarrollo se implementaron módulos clave orientados a profesionalizar la cara pública del sistema para los destinatarios y remitentes, habilitar canales formales de atención, y solucionar limitaciones operativas del panel gerencial que impedían la actualización de envíos antiguos y falseaban las métricas de la flota.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           FORMOPACK EXPRESS                                  │
├─────────────────────┬───────────────────────────┬─────────────────────────────┤
│   CARA AL CLIENTE   │      ATENCIÓN Y SOPORTE   │    GESTIÓN ADMINISTRATIVA   │
│  - Tracking amigable│  - Chats en vivo 1 a 1    │  - Métricas en tiempo real  │
│  - Comprobantes PDF │  - Auto-limpieza de chats │  - Histórico 7 días fiel    │
│  - Credencial retiro│  - Sin acumulación BD     │  - Actualización manual     │
│  - Contacto directo │  - Recepcionista y Admin  │  - Buscador global envíos   │
└─────────────────────┴───────────────────────────┴─────────────────────────────┘
```

---

## 2. Portal de Tracking Público Enriquecido

**Archivos principales:**
- `web/templates/tracking.html`
- `web/routes/admin.py`
- `tests/test_tracking.py`

### 2.1 Descarga de Comprobante / Remito de Entrega
* Cuando un paquete alcanza el estado `entregado`, la interfaz de seguimiento muestra automáticamente un bloque destacado con un botón de **"Descargar Comprobante / Remito"**.
* Permite al destinatario o remitente obtener la constancia oficial de entrega en formato digital/impresión con los datos del envío y el código QR de verificación.

### 2.2 Protocolo de Custodia y Credencial de Retiro
* Si el paquete no pudo ser entregado tras **3 intentos de visita fallidos** o ingresó en circuito de `devolución`:
  1. Se presenta un **banner de alerta visual destacado** notificando que el paquete se encuentra resguardado en almacén central.
  2. Se detalla la dirección exacta de custodia (`Planta Central FormoPack, Formosa Capital`) y los horarios hábiles de atención.
  3. Se habilita el botón interactivo **"Descargar Credencial de Retiro"**, que genera una credencial con el N° de guía, nombre del titular y requisitos (presentación de DNI original) para el retiro en mostrador.

### 2.3 Línea de Tiempo con Explicaciones Claras y Amigables
* Se reemplazaron los registros técnicos crudos por mensajes descriptivos pensados para el usuario final:
  * *"1er intento: Visitamos tu domicilio pero no obtuvimos respuesta."*
  * *"Tu paquete se encuentra clasificado en el centro operativo listo para despacho."*
  * *"Tu paquete ya está en el móvil de reparto camino a tu domicilio."*

### 2.4 Acciones Rápidas del Cliente
* Se integró un botón de **"Contactar a Soporte"** que permite al cliente iniciar una consulta formal por correo electrónico o mediante el sistema de soporte para coordinar cambios de franja horaria o aclaraciones de domicilio.

---

## 3. Módulo de Soporte al Cliente y Atención en Tiempo Real

**Archivos principales:**
- `app/controllers/soporte_controller.py`
- `web/routes/soporte.py`
- `web/templates/soporte/panel.html`
- `web/templates/soporte/chat.html`
- `tests/test_soporte.py`

### 3.1 Canal Centralizado (Reemplazo de WhatsApp)
* Se eliminaron los enlaces externos a WhatsApp para mantener la trazabilidad, privacidad y profesionalismo dentro de la infraestructura de FormoPack.

### 3.2 Concurrencia Exclusiva (1 Operador por Conversación)
* **Regla de negocio:** Un chat solo puede ser tomado por un único agente a la vez (administrador o recepcionista).
* Cuando un operador abre una conversación pendiente, el sistema la asigna exclusivamente a su sesión (`operador_id`), impidiendo que otro usuario responda simultáneamente y genere mensajes contradictorios.

### 3.3 Ciclo de Vida y Auto-Eliminación de Conversaciones
* Con el fin de **no consumir espacio innecesario en la base de datos**, el sistema implementa una política de limpieza al concluir la atención:
  1. Mientras el chat está abierto, figura en estado `en_espera` o `en_progreso`.
  2. Al pulsar **"Finalizar Conversación"**, el chat y sus mensajes asociados son purgados de las tablas activas.
  3. El panel de soporte conserva únicamente los chats que requieren atención viva o están siendo gestionados activamente.

---

## 4. Recuperación Segura de Contraseñas por Correo

**Archivos principales:**
- `app/controllers/auth_controller.py`
- `web/routes/auth.py`
- `web/templates/auth/recuperar_password.html`
- `web/templates/auth/restablecer_password.html`
- `tests/test_recuperacion_password.py`

### 4.1 Validación Exacta del Correo Registrado
* Se implementó una verificación estricta en el controlador: el correo ingresado debe coincidir exactamente con el correo declarado por el usuario al momento de su creación en la base de datos.
* Si el correo no existe o pertenece a un usuario inactivo, se informan los mensajes de validación correspondientes sin exponer datos sensibles del esquema.

### 4.2 Código Seguro de 6 Dígitos y Expiración
* Se genera un código OTP numérico de 6 dígitos con hash criptográfico y tiempo de validez de **15 minutos**.
* Si el servidor tiene configurado Gmail SMTP, se despacha por correo; en caso de entorno de desarrollo local sin credenciales, se genera una notificación informativa para pruebas.
* Se agregó rate limiting (`limiter.limit`) para evitar ataques de fuerza bruta en los formularios de solicitud y restablecimiento.

---

## 5. Corrección Integral del Dashboard y Gestión de Pedidos

**Archivos principales:**
- `web/routes/admin.py`
- `web/templates/admin/dashboard.html`
- `tests/test_dashboard_pedidos.py`

### 5.1 Diagnóstico de Fallas Previas
1. **Falso Cero en Tarjetas Métricas:** La función `_obtener_metricas()` filtraba todas las tarjetas por `WHERE DATE(fecha_creacion) = CURDATE()`. Los pedidos creados en días previos que hoy salían `en_ruta`, tenían intentos `fallidos` o se entregaban (`entregado`), marcaban `0` en el panel.
2. **Gráfica Histórica con Huecos:** Solo se graficaban los días con registros nuevos. Días sin pedidos no aparecían en el eje temporal, y las entregas se atribuían a la fecha de creación del envío en vez de la fecha real en que ocurrió la entrega.
3. **Pedidos Antiguos Congelados:** La tabla mostraba un límite duro de 10 envíos sin buscador ni filtros, y no existía ningún botón ni endpoint para que el personal pudiera actualizar el estado de un envío directamente (solo dependía de la app del chofer).

### 5.2 Solución Implementada: Métricas Operativas en Vivo
Se reestructuró `_obtener_metricas()` dividiendo responsabilidades:
* **Métricas del Día:** Nuevos registros y facturación generada hoy (`DATE(fecha_creacion) = CURDATE()`).
* **Estados Activos de Flota:** 
  * `en_ruta`: Todos los pedidos en reparto independientemente de su fecha de creación.
  * `fallidos`: Incidencias activas, intentos fallidos y devoluciones pendientes.
  * `en_planta`: Paquetes en clasificación en centro logístico.
  * `recibidos`: Envíos recepcionados en espera de despacho.
* **Entregados Hoy:** Consulta sobre `historial_estados` con `WHERE estado = 'entregado' AND DATE(fecha_hora) = CURDATE()`. Cualquier paquete entregado hoy (incluso creado semanas atrás) suma a la métrica.
* **Caja del Día:** Desglose en tiempo real de ingresos en efectivo, pagos digitales y cobros efectuados.

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Registrados Hoy │  │ En Ruta (Vivos) │  │ Entregados Hoy  │  │ Fallidos / Inc. │
│        1        │  │        1        │  │        1        │  │        1        │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 5.3 Gráfica y Tabla de 7 Días Continua
* `_obtener_historico_metricas()` genera una secuencia fija e ininterrumpida de los **últimos 7 días**.
* Cruza `envios` para creaciones y facturación con `historial_estados` para computar las entregas e incidencias en la fecha en que efectivamente ocurrieron.

### 5.4 Buscador Global y Filtros Avanzados de Envíos
Se agregó una barra de filtros en la parte superior del listado de pedidos:
* **Búsqueda por texto libre (`q`):** Coincidencia parcial o exacta por N° de Guía (`FPX-...`), nombre de remitente, nombre de destinatario o localidad de destino.
* **Filtro por estado operativo (`estado`):** Permite listar únicamente `recibido`, `en_planta`, `en_ruta`, `entregado`, `fallido`, `devolucion` o `siniestro`.
* **Selector de límite (`limite`):** Opciones para 10, 25, 50, 100 o "Todos" los envíos históricos.

### 5.5 Modal y Endpoint para Actualizar Cualquier Envío
* Cada fila del listado incorpora el botón **"Actualizar"** con un modal interactivo:
  * Selección del nuevo estado operativo.
  * Ubicación del movimiento (ej: *Planta Central*, *Sucursal Clorinda*).
  * Observación detallada del cambio.
* **Endpoint seguro:** `POST /admin/envios/<id_envio>/actualizar-estado`:
  1. Valida el estado contra la lista oficial permitida.
  2. Actualiza `envios.estado_actual` y la bandera `es_devolucion`.
  3. Registra una nueva entrada en `historial_estados` con fecha y hora para auditoría y trazabilidad pública.
  4. Dispara una notificación por correo electrónico asíncrono al cliente mediante `notificar_cambio_estado_async()`.

---

## 6. Corrección de Navegación, Roles y Redirecciones

**Archivos principales:**
- `web/routes/auth.py`
- `web/routes/recepcion.py`
- `web/templates/base.html`

1. **Redirección de Recepcionista Corregida:**
   * En `web/routes/auth.py`, la redirección tras iniciar sesión apuntaba a `recepcion.inicio` (ruta inexistente que arrojaba `BuildError`).
   * Se ajustó para que los usuarios con rol `recepcionista` o `administrador` ingresen directamente al Dashboard (`admin.dashboard`).
2. **Acceso al Panel de Control para Recepcionistas:**
   * En la barra de navegación lateral (`base.html`), el enlace **"Panel de Control"** estaba restringido exclusivamente al rol `administrador`.
   * Se movió a la sección de **Operaciones**, quedando disponible tanto para `administrador` como para `recepcionista`, permitiendo que el personal de mostrador pueda supervisar y actualizar los pedidos.
3. **Depuración de Redirecciones Rotas:**
   * En `web/routes/recepcion.py`, se reemplazaron las llamadas erróneas a `recepcion.dashboard` por `admin.dashboard`.

---

## 7. Batería de Pruebas y Validación

Se crearon suites de pruebas dedicadas para verificar la correcta integración de todos los componentes nuevos:

| Archivo de Test | Pruebas Principales | Resultado |
|---|---|:---:|
| `tests/test_tracking.py` | Tracking público, comprobantes, credencial de retiro en custodia, línea de tiempo amigable. | ✅ Passed |
| `tests/test_soporte.py` | Panel de soporte, concurrencia de 1 operador, auto-eliminación al finalizar, validaciones. | ✅ Passed |
| `tests/test_recuperacion_password.py` | Coincidencia de email, generación de token 6 dígitos, expiración 15m, cambio de password. | ✅ Passed |
| `tests/test_dashboard_pedidos.py` | Métricas operativas vivas, histórico 7 días continuo, buscador global, modal y endpoint de actualización de envíos, renderizado para admin y recepcionista. | ✅ Passed |

### Ejecución Integral del Test Suite
```bash
pytest -q
============================== 92 passed in 2.60s ==============================
```

Todas las pruebas del sistema ejecutan de manera limpia, garantizando estabilidad operativa y compatibilidad total con la base de datos MySQL y la arquitectura Flask.
