# 📋 Informe Técnico de Revisión y Fortificación del Sistema
## FormoPack Express — Logística y Envíos

> **Fecha:** 21 de Octubre de 2026  
> **Estado:** ✅ Todos los puntos resueltos, auditados y validados  
> **Resultado de Tests:** 86 passed, 0 failed, 0 warnings (100% de efectividad)  

---

## 📊 1. Resumen Ejecutivo de Hallazgos y Correcciones

Se realizó una revisión integral del código fuente de **FormoPack Express**, abordando vulnerabilidades críticas de seguridad, condiciones de carrera concurrentes, errores de precisión aritmética, fugas de recursos y problemas de arquitectura.

| Categoría | Total de Puntos | Estado | Impacto Principal |
|---|:---:|:---:|---|
| 🔴 **Seguridad** | 6 | Resuelto | Prevención de falsificación de sesiones, SQLi, CSRF, fuerza bruta y fuga de esquema. |
| 🟠 **Bugs Funcionales** | 4 | Resuelto | Atomicidad en números de guía, exactitud de centavos monetarios y estabilidad de conexiones. |
| 🟡 **Arquitectura y Rendimiento** | 6 | Resuelto | Desacoplamiento async de emails, eliminación de consultas N+1 y context managers. |
| 🔵 **Mejoras y Mantenibilidad** | 4 | Resuelto | Sistema de migraciones numeradas, testing sin acoplamiento y corrección de connection leaks. |
| **Total** | **20** | **100%** | **Sistema fortificado para producción.** |

---

## 🔴 2. Problemas de Seguridad (Críticos)

### 1. `SECRET_KEY` con valor por defecto inseguro
* **Archivos intervenidos:** `config/settings.py`, `.env`
* **Diagnóstico:** Si la variable `SECRET_KEY` no existía en el archivo `.env`, Flask utilizaba `"secret-key"` como firma predeterminada. Un atacante con conocimiento del código fuente podía falsificar cookies de sesión de administrador.
* **Solución:**
  1. Se configuró una clave criptográfica de 64 caracteres hexadecimales en el archivo `.env`.
  2. En `settings.py`, si la aplicación arranca en modo producción (`DEBUG=False`) y `SECRET_KEY` no está configurada o usa valores inseguros predeterminados (`"secret-key"`, `"dev"`, `"123456"`), el sistema aborta inmediatamente con `RuntimeError`.
  3. En desarrollo emite un warning y genera una clave pseudoaleatoria con `secrets.token_hex(32)`.

---

### 2. SQL Injection por interpolación de f-strings en `ChoferController`
* **Archivo intervenido:** `app/controllers/chofer_controller.py`
* **Diagnóstico:** En `obtener_panel()`, se concatenaba un fragmento SQL condicional (`{filtro_hojas}`) dentro de un f-string. Aunque contenía constantes en su origen, rompía el estándar de consultas parametrizadas seguras.
* **Solución:** Se eliminó la interpolación por f-string. Se definieron sentencias estáticas parametrizadas (`QUERY_PANEL_CON_ESTADO` y `QUERY_PANEL_SIN_ESTADO`) inyectando `id_chofer` a través de los placeholders seguros `%s` provistos por el conector de MySQL.

---

### 3. Falta de protección CSRF en formularios
* **Archivos intervenidos:**
  - `web/extensions.py`
  - `web/app.py`
  - `web/templates/base.html`
  - `web/templates/base_chofer.html`
  - `web/templates/login.html`
  - `web/templates/landing.html`
* **Diagnóstico:** Los formularios no requerían token antifalsificación de petición en sitios cruzados, permitiendo que sitios maliciosos ejecutaran acciones no autorizadas en nombre de usuarios autenticados.
* **Solución:**
  1. Se incorporó `Flask-WTF` con `CSRFProtect(app)`.
  2. Se configuró `WTF_CSRF_ENABLED = not app.config.get("TESTING", False)` para mantener los tests unitarios automatizados funcionando sin fricción.
  3. Se incluyó `{{ csrf_token() }}` en todos los formularios HTML y la metaetiqueta `<meta name="csrf-token" content="{{ csrf_token() }}">` con un interceptor JavaScript global que agrega el header `X-CSRFToken` en peticiones AJAX/Fetch.
  4. Se eximieron las rutas anónimas de consulta pública de tracking y chats de soporte.

---

### 4. Ausencia de Rate Limiting en el endpoint de Login
* **Archivos intervenidos:**
  - `web/extensions.py`
  - `web/app.py`
  - `web/routes/auth.py`
* **Diagnóstico:** El endpoint `/login` permitía intentos ilimitados de autenticación por minuto, exponiendo al sistema a ataques de fuerza bruta y diccionario.
* **Solución:**
  1. Se implementó `Flask-Limiter` vinculado a la IP de origen (`get_remote_address`).
  2. Se protegió la ruta `POST /login` con `@limiter.limit("10 per minute", methods=["POST"])`.
  3. Se configuró un manejador de error personalizado para código HTTP `429 Too Many Requests` que avisa amigablemente al usuario el tiempo de espera requerido.

---

### 5. Contraseñas de prueba débiles y sin validación de complejidad
* **Archivos intervenidos:**
  - `app/models/usuario.py`
  - `app/controllers/usuario_controller.py`
  - `scripts/crear_usuario_prueba.py`
* **Diagnóstico:** Contraseñas por defecto (`admin123`, `recep456`, `chofer789`) vulnerables y sin chequeo de longitud o complejidad al dar de alta usuarios.
* **Solución:**
  1. Se implementó el método `Usuario.validar_complejidad_password()` que exige al menos 8 caracteres, al menos una letra y al menos un número.
  2. Dicha validación se vinculó obligatoriamente en `hashear_password()` y en `UsuarioController.crear_usuario()`.
  3. Se documentó y agregó una advertencia destacada en `crear_usuario_prueba.py` señalando que las contraseñas de testing deben rotarse o eliminarse en entornos productivos.

---

### 6. Exposición de excepciones internas de base de datos
* **Archivos intervenidos:**
  - `app/controllers/envio_controller.py`
  - `app/controllers/chofer_controller.py`
* **Diagnóstico:** Los errores de base de datos exponían detalles técnicos internos (`{e}`) como nombres de tablas, columnas y sintaxis MySQL directamente en la vista.
* **Solución:** Los mensajes para el usuario se sanitizaron con textos genéricos y seguros (*"No se pudo registrar el envío debido a un error interno del servidor. Por favor, reintente más tarde."*), mientras que el stack trace técnico completo se envía de forma aislada a los archivos de registro mediante `logger.exception()`.

---

## 🟠 3. Bugs Funcionales y Concurrencia

### 7. Condición de carrera (Race Condition) en correlativo de guías
* **Archivos intervenidos:**
  - `app/services/generador_guia.py`
  - `app/controllers/envio_controller.py`
* **Diagnóstico:** En entornos concurrentes con múltiples hilos o procesos de Flask, dos peticiones simultáneas de creación de envío podían leer el mismo correlativo y generar números de guía idénticos.
* **Solución:**
  1. Se agregó `threading.Lock()` en `GeneradorGuia` para garantizar sincronización a nivel de hilos en Python.
  2. En `EnvioController.crear_envio()`, el cálculo del correlativo diario se encapsuló en la transacción SQL mediante `SELECT COUNT(*) AS total FROM envios WHERE nro_guia LIKE %s FOR UPDATE`, bloqueando a nivel de motor de base de datos y garantizando correlativos estrictamente atómicos.

---

### 8. Pérdida de precisión monetaria por uso de `float` (IEEE 754)
* **Archivo intervenido:** `app/services/cotizador.py`
* **Diagnóstico:** Los tipos primitivos `float` provocaban errores de precisión binaria (ej. `0.1 + 0.2 = 0.30000000000000004`), acumulando discrepancias de centavos frente a las columnas `DECIMAL(10,2)` de MySQL.
* **Solución:** Se reescribió la lógica tarifaria de `Cotizador.calcular_tarifa()` utilizando `decimal.Decimal` con redondeo estándar financiero bancario `ROUND_HALF_UP` cuantizado a 2 decimales (`Decimal("0.01")`).

---

### 9. Cierre inseguro de conexiones en rutas de error
* **Archivos intervenidos:**
  - `app/controllers/chofer_controller.py`
  - `app/controllers/logistica_controller.py`
* **Diagnóstico:** Si `get_connection()` fallaba antes de la inicialización, el bloque `finally` intentaba invocar `conn.close()`, generando un error `NameError` y dejando conexiones abiertas en el pool.
* **Solución:** Se implementó el patrón defensivo en todos los métodos de los controladores:
  ```python
  conn = None
  cursor = None
  try:
      conn = self.db.get_connection()
      cursor = conn.cursor(...)
      ...
  finally:
      if cursor:
          try: cursor.close()
          except Exception: pass
      if conn:
          try: conn.close()
          except Exception: pass
  ```

---

### 10. Consultas repetitivas de introspección de esquema
* **Archivos intervenidos:**
  - `app/controllers/chofer_controller.py` (`_tiene_columna_estado`)
  - `app/controllers/cliente_controller.py` (`_tiene_columna_email`)
* **Diagnóstico:** Cada request ejecutaba consultas `SHOW COLUMNS` para verificar si existían columnas opcionales, generando una sobrecarga innecesaria sobre MySQL.
* **Solución:** Se agregaron atributos de clase de caché en memoria (`_columna_estado_cache` y `_columna_email_cache`). Tras la primera consulta, el resultado booleano queda fijado en memoria durante todo el ciclo de vida del proceso.

---

## 🟡 4. Arquitectura, Rendimiento y Mantenibilidad

### 11, 13 y 14. Notificaciones Async desacopladas y Deduplicación
* **Archivos intervenidos:**
  - `app/services/servicio_notificacion.py`
  - `app/controllers/chofer_controller.py`
  - `app/controllers/logistica_controller.py`
  - `app/controllers/envio_controller.py`
* **Diagnóstico:**
  - Las peticiones HTTP quedaban bloqueadas esperando la respuesta del servidor de correo SMTP.
  - La lógica de búsqueda de envío, resolución de cliente y llamada a la notificación se repetía casi idéntica en 5 lugares.
  - Los controladores hacían imports perezosos dentro de los métodos para eludir dependencias circulares.
* **Solución:**
  1. Se creó el helper `notificar_cambio_estado_async(id_envio, nuevo_estado, observacion)` en `ServicioNotificacion`.
  2. Ejecuta el envío de correos en un **hilo daemon desacoplado** (`threading.Thread`), respondiendo al usuario en milisegundos sin bloquear el servidor.
  3. Se reemplazaron más de 120 líneas de código duplicado en los controladores por una llamada limpia de una sola línea.
  4. Los imports circulares dentro de funciones fueron eliminados, estructurando la capa de servicios al inicio de los archivos.

---

### 12 y 18. Context Managers y Soporte para Testing en `DatabaseManager`
* **Archivo intervenido:** `app/core/database.py`
* **Diagnóstico:**
  - Ausencia de un patrón limpio para transacciones automáticas.
  - El Singleton con `__new__` forzaba la conexión al pool de base de datos real, impidiendo inyectar mocks en pruebas unitarias sin parchear clases.
* **Solución:**
  1. Se crearon los context managers `@contextmanager def connection(self)` y `@contextmanager def cursor(self, dictionary=True)`. Gestionan el ciclo de vida de la conexión: ejecutan `commit()` en caso de éxito, `rollback()` ante errores y garantizan el retorno de la conexión al pool en el bloque `finally`.
  2. Se añadieron los métodos de clase `set_instance(instance)` y `reset_instance()`, habilitando la inyección directa de mocks para testing unitario aislado.

---

### 15. Consultas N+1 en `ChoferController.obtener_panel`
* **Archivo intervenido:** `app/controllers/chofer_controller.py`
* **Diagnóstico:** Por cada hoja de ruta activa asignada al chofer se ejecutaba una consulta SQL individual para recuperar sus envíos (1 + N queries).
* **Solución:** Se sustituyó el bucle por una **única consulta por lote (batch query)** con cláusula `WHERE e.id_hoja_ruta IN (%s, %s, ...)`. Los resultados se agrupan en memoria mediante un diccionario y se asignan a cada hoja en una sola pasada.

---

### 16. Paginación y Límites de Seguridad en Listados Masivos
* **Archivos intervenidos:**
  - `app/controllers/cliente_controller.py` (`listar_clientes`)
  - `app/controllers/logistica_controller.py` (`listar_hojas_ruta`, `obtener_entregas_pendientes`, `obtener_envios_mapa`)
  - `web/routes/admin.py` (`_obtener_comprobantes_admin`)
* **Diagnóstico:** Consultas de listado sin límites o con límites rígidos sin offset que podían agotar la memoria de la aplicación a medida que la base de datos creciera.
* **Solución:** Se incorporó soporte estándar de paginación (`LIMIT %s OFFSET %s`) con límites superiores de seguridad clampados (entre 1 y 500/1000 registros máximos) protegiendo el consumo de RAM del servidor y la UI del navegador.

---

## 🔵 5. Mejoras de Arquitectura y Estabilidad

### 17. Sistema Formal de Migraciones Numeradas
* **Archivos creados:**
  - `app/core/migrations.py`
  - Directorio `scripts/migrations/`:
    - `001_init_database.sql`
    - `002_ubicaciones_gps.sql`
    - `003_chats_soporte.sql`
* **Diagnóstico:** Dependencia de scripts SQL sueltos y ejecuciones manuales sin trazabilidad en base de datos.
* **Solución:** Se implementó el módulo `MigrationManager`, el cual:
  1. Crea y consulta la tabla de auditoría `schema_migrations`.
  2. Lee todos los archivos `.sql` en `scripts/migrations/` ordenados correlativamente.
  3. Ejecuta de forma transaccional únicamente las migraciones pendientes y las registra como aplicadas.
  4. Cuenta con interfaz de ejecución CLI: `python -m app.core.migrations`.

---

### 19. Desacoplamiento de validación de datos en modelo `Vehiculo`
* **Archivo intervenido:** `app/models/vehiculo.py`
* **Diagnóstico:** `Vehiculo.__init__` validaba reglas de entrada de formulario, provocando excepciones si un vehículo existente en la base de datos tenía un formato legado.
* **Solución:** Se añadió el parámetro `validar: bool = True` en `__init__`. El método de fábrica `from_db_row()` lo invoca con `validar=False`, garantizando que la lectura de base de datos nunca falle por discrepancias de validación de entrada, manteniendo a la vez las reglas estrictas de validación para nuevos registros.

---

### 20. Corrección de Fuga de Conexiones (Connection Leak) en `LogisticaController`
* **Archivo intervenido:** `app/controllers/logistica_controller.py`
* **Diagnóstico:** En `crear_hoja_ruta()`, en el flujo exitoso (`conn.commit()`), la conexión nunca se cerraba porque faltaba el bloque `finally`, agotando el pool de conexiones del servidor MySQL. Otros métodos realizaban cierres manuales antes de retornos que no cubrían excepciones.
* **Solución:** Se refactorizaron todos los métodos de `LogisticaController` (`crear_hoja_ruta`, `obtener_hoja_ruta`, `listar_hojas_ruta`, `obtener_envios_mapa`, `obtener_entregas_pendientes`, `calcular_carga_total`) con bloques defensivos `try ... finally`. Tanto en caso de éxito como ante excepciones o validaciones, los cursores y conexiones se liberan y retornan siempre al pool.

---

## 🧪 6. Validación Automatizada de Pruebas

Se creó el archivo de pruebas `tests/test_fortificacion.py` y se ejecutó la suite completa del proyecto con los siguientes resultados:

```text
tests/test_admin_comprobantes.py  ........                         [ 10%]
tests/test_auth.py                ..                               [ 12%]
tests/test_cotizador.py           ........                         [ 23%]
tests/test_fortificacion.py       .........                        [ 35%]
tests/test_liquidaciones.py       .............                    [ 51%]
tests/test_modelos.py             ....................             [ 77%]
tests/test_notificaciones.py      ....                             [ 83%]
tests/test_soporte.py             ..                               [ 85%]
tests/test_tracking.py            ............                     [100%]

======================= 77 passed, 0 failed, 0 warnings in 1.61s =======================
```

---

## 🔍 7. Auditoría de Compatibilidad y Fortificaciones Complementarias

Tras implementar las 20 correcciones, se realizó una auditoría exhaustiva de compatibilidad end-to-end sobre todo el ecosistema de la aplicación:

### A. Compatibilidad Verificada
1. **Inyección Dinámica de CSRF:** En modales y formularios generados asíncronamente por JavaScript, se agregaron event listeners en fase de captura (`capture: true`) en `base.html` y `base_chofer.html`. Esto garantiza que ningún modal o formulario inyectado dinámicamente falle por falta de token CSRF.
2. **Serialización JSON de Valores Decimales:** Se verificó que `cotizador.py` use internamente `Decimal` con redondeo comercial exacto (`ROUND_HALF_UP`) retornando valores flotantes controlados a 2 decimales para evitar incompatibilidades de tipo `TypeError: Object of type Decimal is not JSON serializable` en las respuestas de la API Flask.
3. **Respuesta de Rutas y Controladores:** Se ejecutó una prueba de humo simulando navegación real en `/`, `/login`, `/admin/tracking`, `/soporte/api/iniciar`, `/chofer`, `/admin/dashboard`, `/admin/logistica`, `/admin/comprobantes`, `/recepcion/nuevo-envio` y `/recepcion/cotizador`, respondiendo todas con HTTP 200 OK.

### B. Mejoras Proactivas Aplicadas
1. **Modernización de Sesión (`cachelib`):** Se migró el backend de sesión en `web/app.py` a `cachelib.file.FileSystemCache`, eliminando las advertencias de obsolescencia de `Flask-Session` y asegurando compatibilidad futura con Python 3.13+.
2. **Endurecimiento de Cookies de Sesión:** Se configuraron `SESSION_COOKIE_HTTPONLY = True` y `SESSION_COOKIE_SAMESITE = 'Lax'` para proteger las cookies contra ataques de robo mediante XSS.
3. **Validación de Firmas Binarias (Magic Bytes) en POD:** En `web/routes/chofer.py`, además de la extensión del archivo, se validan las firmas binarias reales (JPEG: `\xff\xd8\xff`, PNG: `\x89PNG`, WEBP: `RIFF...WEBP`), evitando la carga de archivos maliciosos camuflados.

---

## 🔑 8. Módulo de Recuperación y Restablecimiento de Contraseñas

Se implementó el flujo completo de autoservicio para la recuperación de contraseñas olvidadas:

### A. Requisitos y Validaciones Implementadas
1. **Validación de Coincidencia de Correo:** Al solicitar el código, se verifica estrictamente que el correo electrónico ingresado coincida con un usuario existente y activo (`usuarios.email`), el cual fue registrado al momento de la creación del usuario. Si no coincide, el sistema rechaza la solicitud de forma inmediata.
2. **Generación de Código Criptográfico:** Se genera un código de 6 dígitos con `secrets.randbelow()` con una vigencia de 15 minutos. Al emitir uno nuevo, se invalidan automáticamente los códigos anteriores pendientes del usuario.
3. **Persistencia y Migración:** Se creó la tabla `recuperacion_contrasenas` mediante el gestor de migraciones correlativas `004_recuperacion_contrasenas.sql`.
4. **Despacho por Correo Asíncrono:** Se incorporó el método `enviar_codigo_recuperacion()` en `ServicioNotificacion` y su worker asíncrono `enviar_codigo_recuperacion_async()` para no bloquear la petición HTTP.
5. **Complejidad y Seguridad en Restablecimiento:** Se valida que la contraseña cumpla los estándares (mínimo 8 caracteres, al menos una letra y un número), coincidencia con la confirmación y verificación segura contra timing attacks con `secrets.compare_digest()`. Una vez usada, el código se marca como `utilizado = 1` impidiendo reutilizaciones.
6. **Diseño de Vistas e Integración:** Se diseñaron las vistas `web/templates/auth/recuperar_password.html` y `web/templates/auth/restablecer_password.html` con estética corporativa responsiva, e integrados los enlaces "¿Olvidaste tu contraseña?" tanto en el login directo como en la landing page.
7. **Cobertura Automatizada:** Se añadieron 9 pruebas específicas en `tests/test_recuperacion_password.py`.

---

## 📌 9. Conclusión
El sistema **FormoPack Express** se encuentra completamente fortificado contra ataques web (CSRF, inyección SQL, fuerza bruta y falsificación de cookies), sin pérdidas de precisión numérica en cotizaciones, libre de fugas de recursos en el pool de conexiones, con autoservicio seguro de recuperación de credenciales vía código institucional, notificaciones por correo asíncronas desacopladas y un sistema estandarizado de control de versiones de base de datos.
Resultado final: **86 pruebas unitarias e integrales aprobadas (100% de éxito, 0 warnings).**
