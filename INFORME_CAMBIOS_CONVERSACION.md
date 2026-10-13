# Informe de modificaciones de FormoPack

**Fecha:** 16 de octubre de 2026  
**Proyecto:** FormoPack Express  
**Alcance:** Cambios y decisiones tratados durante esta conversación, más el historial reciente del repositorio que ayuda a contextualizarlos.

## 1. Resumen

Se trabajó en el arranque y despliegue de la aplicación, la sincronización Git, la presentación del mapa logístico y el seguimiento de paquetes. El chofer puede compartir voluntariamente el GPS durante una ruta activa; ahora el mapa público y el mapa global de administración pueden mostrar el último punto reciente asociado a esa ruta.

El GPS requiere HTTPS fuera de `localhost`, permiso del navegador y que el panel del chofer permanezca abierto. No equivale a rastreo permanente en segundo plano.

## 2. Cambios funcionales y técnicos

### Seguimiento público de envíos

- Se reorganizó la vista pública en [web/templates/tracking.html](web/templates/tracking.html): número de guía y estado actual más visibles, progreso, destino, historial cronológico y acciones para compartir el enlace por WhatsApp/SMS o copiarlo.
- La hora y el estado se obtienen del historial consultado en la base de datos.
- Se agregó recarga automática cada 60 segundos para envíos en curso y un control para actualizar manualmente.
- Se aclaró que la línea del mapa por localidad es referencial; no representa calles recorridas ni ubicación GPS.
- No se muestra una hora exacta de llegada porque el sistema no cuenta con datos suficientes para calcularla de forma confiable.
- La ruta de [web/routes/admin.py](web/routes/admin.py) entrega a la vista el resumen del envío y el último punto GPS disponible.

### Ubicación GPS durante una ruta

- Se agregó al panel [web/templates/chofer/panel.html](web/templates/chofer/panel.html) el botón explícito **Compartir ubicación en ruta** y la opción de detener el envío.
- El navegador solicita permiso y reporta coordenadas con una frecuencia limitada; la interfaz informa si espera permiso, no hay señal, se denegó el acceso o se sincronizó la posición.
- Se agregó en [web/routes/chofer.py](web/routes/chofer.py) un endpoint autenticado que recibe las coordenadas.
- [app/controllers/chofer_controller.py](app/controllers/chofer_controller.py) verifica que la hoja pertenezca al chofer y tenga envíos activos en ruta, valida rangos de latitud/longitud y guarda solo la ubicación más reciente por hoja.
- El tracking público usa el GPS de una ruta `en_ruta` solo si fue actualizado en los últimos cinco minutos. Para un envío entregado o fallido puede mostrar la última coordenada guardada en el intento de entrega, identificándola como histórica.
- En `recibido` y `en_planta` el mapa permanece en planta: todavía no hay movimiento GPS de ruta que mostrar.

### Base de datos

- Se añadió la tabla `ubicaciones_hojas_ruta` a [scripts/init_database.sql](scripts/init_database.sql) para instalaciones nuevas.
- Se creó [scripts/migracion_ubicaciones_gps.sql](scripts/migracion_ubicaciones_gps.sql), migración idempotente para bases existentes.
- La migración se ejecutó y se verificó en la base MySQL local durante esta sesión. Debe ejecutarse también en cualquier base remota, como la de Render.

### Mapa y panel de logística

- Se ajustó el layout de [web/templates/admin/logistica.html](web/templates/admin/logistica.html) para evitar alturas rígidas y recortes en el mapa y en los paneles laterales de ruta, leyenda y próximas entregas.
- Se convirtió el mapa en una vista global: incluye selector de guía, opción de ver todos los envíos, detalle del envío seleccionado y actualización periódica desde un endpoint administrativo.
- La leyenda ahora tiene filtros seleccionables para Planta, Pendientes, En tránsito, Demora / problema y Entregados; cada categoría muestra su conteo y filtra a la vez los marcadores y las guías seleccionables.
- Al filtrar pocos paquetes, el mapa ahora amplía el zoom para que GPS cercanos a la planta no queden ocultos por el marcador azul. Los puntos GPS conservan el color correspondiente al estado del paquete.
- Se añadieron coordenadas aproximadas verificadas para `Formosa Capital`, `San Martín Dos`, `Villa Dos Trece` y `Estanislao del Campo`; las localidades sin coordenadas confiables no reciben una ubicación inventada.
- El mapa usa el GPS reciente del vehículo para envíos activos; si no hay GPS, muestra la localidad de destino solo como referencia. Los envíos de una misma hoja comparten la ubicación del vehículo.
- El endpoint `GET /admin/logistica/mapa/envios` requiere sesión y rol autorizado.
- La consulta global recupera todos los envíos registrados; durante la prueba local devolvió 7 envíos y 0 ubicaciones GPS activas.
- En la base local durante esta verificación había 2 pendientes, 1 envío con problema, 3 entregados y 1 en tránsito; todos quedaron asignados a una categoría visible.

### Arranque y despliegue

- Se creó [wsgi.py](wsgi.py) en la raíz para exponer la aplicación factory Flask como `app`.
- Se indicó usar `gunicorn wsgi:app` como comando de inicio en Render y `pip install -r requirements.txt` como comando de build.
- **Pendiente:** [requirements.txt](requirements.txt) todavía no incluye Gunicorn, por lo que la configuración de Render necesita esa dependencia antes de poder arrancar con ese comando.
- La conversación también cubrió configuración de variables de entorno, servicios gratuitos y planes de Render. Son instrucciones de despliegue, no una confirmación de que la app ya esté desplegada.

### Git y archivos locales

- En el historial reciente consta el commit `3ad3622` (`chore: ignore .flask_session and remove from tracking`), que agregó `.flask_session/` a [.gitignore](.gitignore) y retiró archivos de sesión del índice.
- También se creó `wsgi.py`; no se debe versionar `.env`, `.venv` ni archivos temporales de sesión.
- Durante la conversación se resolvió un push rechazado integrando commits remotos y se mostró una salida de push exitoso. **Sin embargo, el estado actual del repositorio volvió a cambiar y no debe considerarse limpio ni sincronizado sin resolver los puntos de la sección 5.**

## 3. Historial reciente reflejado en commits

Los commits recientes también registran estos trabajos del proyecto:

- Mejoras de clientes, validaciones de recepción/logística y sus pruebas (`19a28b7`).
- Correcciones de reenvío de formularios mediante PRG (`8d3d628`).
- Mapa interactivo Leaflet, ajuste de coordenadas de localidades y mejoras de recursos locales/offline (`4a65eff`, `ef1b939`, `b26c0db`).
- Documentación de instalación y archivo `.env.example` (`f3da963`).
- Favicon corporativo (`a548041`).
- Exclusión de `.flask_session` del control de versiones (`3ad3622`).

Estos puntos se citan como historial que aparece en Git; no todos corresponden necesariamente a cambios sin commit de esta sesión.

## 4. Validaciones realizadas

- `py_compile` pasó para los módulos Python modificados.
- Las plantillas Jinja de seguimiento y panel del chofer compilaron correctamente.
- Se hizo un render de prueba de la página de seguimiento con un punto GPS de ejemplo; se comprobó que el HTML incluya las coordenadas y el aviso de GPS.
- Pasaron seis pruebas existentes de tracking ejecutadas directamente. `pytest` no estaba instalado en el Python disponible, así que no se ejecutó el runner completo.
- El endpoint global del mapa devolvió HTTP 200 con rol administrador y los 7 envíos de la base MySQL local.
- La vista de logística se renderizó con el selector global y la URL de actualización presentes.
- Se renderizaron y verificaron los cinco controles de filtro por estado en la vista administrativa.
- `git diff --check` no informó errores de whitespace.
- La tabla GPS quedó presente en la base local tras ejecutar la migración.
- No se hizo una prueba de campo con GPS físico ni una verificación final de la app en navegador.

## 5. Pendientes y estado actual

- El estado de Git observado al preparar este informe es **`HEAD (no branch)`** y existe un conflicto sin resolver bajo `.flask_session/79bc207...`. También hay cambios staged y unstaged en varios archivos.
- Por lo anterior, no se puede afirmar que el estado actual completo esté en GitHub ni conviene hacer más `pull`, `push` o `rebase` hasta revisar y resolver el conflicto preservando los cambios.
- Agregar Gunicorn a `requirements.txt` antes del despliegue en Render.
- Ejecutar `scripts/migracion_ubicaciones_gps.sql` en la base remota.
- Probar en un teléfono/navegador HTTPS con permiso GPS y una hoja de ruta activa; comprobar luego el tracking público.
- Una captura anterior mostró valores privados del `.env`. Rotar la contraseña de la base de datos y `SECRET_KEY` si esos valores siguen vigentes; no incluirlos en el repositorio ni en capturas.

## 6. Rutas principales

- [web/templates/tracking.html](web/templates/tracking.html): experiencia pública de seguimiento y mapa.
- [web/templates/chofer/panel.html](web/templates/chofer/panel.html): control para compartir ubicación del chofer.
- [web/routes/chofer.py](web/routes/chofer.py): endpoint protegido de GPS.
- [app/controllers/chofer_controller.py](app/controllers/chofer_controller.py): autorización, validación y persistencia del punto.
- [web/routes/admin.py](web/routes/admin.py): consulta pública de envío, historial y última ubicación.
- [app/controllers/logistica_controller.py](app/controllers/logistica_controller.py): consulta global para el mapa de administración.
- [README.md](README.md): instrucciones de instalación y migración para bases existentes.
- [scripts/migracion_ubicaciones_gps.sql](scripts/migracion_ubicaciones_gps.sql): migración para bases existentes.
- [scripts/init_database.sql](scripts/init_database.sql): esquema para instalaciones nuevas.
- [wsgi.py](wsgi.py): punto de entrada WSGI para el despliegue.
