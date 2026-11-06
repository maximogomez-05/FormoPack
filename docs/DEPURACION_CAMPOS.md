# Depuración de campos y flujos · cierre del 6 de noviembre de 2026

## Alcance y entorno

Revisión del código, validaciones de entrada, formularios y regresiones automatizadas. Las pruebas usan MariaDB desechable en loopback, puerto 33894, bases temporales y Chrome local con Playwright. No se modificó el VPS, su base, las credenciales ni el pago real existente. Los servicios externos se simulan en los recorridos que los requieren. Los requisitos académicos y diagramas quedan para la etapa final.

## Inventario de controles revisados

| Área | Entradas y reglas principales | Persistencia y comprobaciones |
| --- | --- | --- |
| Clientes y recepción | DNI de 7 a 15 dígitos; nombre hasta 100 caracteres con normalización Unicode; teléfono hasta 20 caracteres; correo hasta 100; dirección hasta 200; localidad válida | DNI único, identidad existente inmutable, autocompletado, transacción del alta e identificación de solicitudes repetidas |
| Bultos y cotización | De 1 a 100 bultos; listas consistentes; peso real positivo, volumétrico no negativo; dos decimales; fragilidad válida; importes dentro del rango permitido | Tipos DECIMAL, validación de referencias y rechazo previo a escrituras |
| Caja y cobro | Fondo inicial no negativo; importe correspondiente al envío; efectivo entregado suficiente; referencia digital acotada | Un cobro no debe duplicar ingresos; el vuelto no es recaudación; operaciones y cierre transaccionales |
| Mercado Pago | Identificación de orden, importe, receptor, estado y firma de notificación | Regresiones con respuestas simuladas, conciliación e idempotencia; no se realizaron cobros reales |
| Vehículos y despacho | Patente de 3 a 10 caracteres con letras y números, guion permitido; capacidad positiva con dos decimales; despacho de 1 a 20 caracteres; IDs positivos y envíos sin duplicados | Capacidad DECIMAL(10,2), chofer y vehículo disponibles, permisos y asignación de carga |
| GPS y reparto | Latitud entre -90 y 90, longitud entre -180 y 180; precisión opcional entre 0 y 999999.99 metros | Coordenadas a siete decimales, precisión a dos; ruta activa del chofer; un punto rechazado conserva el anterior |
| Usuarios y perfil | Roles permitidos, correo y nombre acotados; contraseña personal de al menos 12 caracteres con letra y número, máximo de 72 bytes UTF-8 | Edición de perfil propio, cambio inicial obligatorio, sesiones y permisos cubiertos por regresiones existentes |
| Evidencias y archivos | Validación del contenido de imágenes, tamaños y firma visible; avatar normalizado | Almacenamiento privado, autorización para documentos y pruebas de respaldo |
| Soporte y reportes | Texto y mensajes acotados, filtros de fecha y estado | Aislamiento de conversaciones, exclusividad de atención y protección de textos exportados a CSV |

Los máximos técnicos no equivalen a límites comerciales nuevos. En logística se alineó el HTML con las reglas que ya aplicaba el servidor. Si se desea un máximo comercial menor para capacidad, debe cambiarse conjuntamente en ambas capas.

## Fallos reproducidos y correcciones

1. **Nombres validados pero guardados sin normalizar.** Un nombre con acentos descompuestos podía superar VARCHAR(100) aunque su forma normalizada fuera válida. La solicitud ahora conserva y persiste los valores normalizados de nombre, DNI, teléfono y correo. Prueba con 100 caracteres acentuados y lectura posterior desde MariaDB.
2. **Capacidad convertida antes de validarla.** La conversión a float ocultaba decimales adicionales y aceptaba booleanos al construir el modelo. Se valida el valor original antes de convertirlo, tanto desde HTTP como desde el modelo.
3. **GPS mal formado o fuera del rango SQL.** Se aceptaban booleanos como coordenadas y no se validaba la precisión del sensor. Se exige un objeto JSON, se validan tipos y rangos, y se redondean únicamente mediciones válidas. Se verifica que los rechazos no sobrescriban el último punto.
4. **Campos escalares repetidos.** El formulario podía enviar dos DNI, modalidades, importes o identificadores y el servidor escogía uno silenciosamente. Recepción, cobro, caja y logística rechazan la ambigüedad; las listas legítimas de bultos y envíos siguen admitidas.
5. **Sintaxis numérica inesperada.** Decimal admitía guiones bajos, dígitos Unicode y espacios de control. Se valida la sintaxis antes de interpretar el número. Se conservan los decimales ordinarios y la notación exponencial válida dentro de los límites.
6. **Cliente desbloqueado después de un formulario rechazado.** La búsqueda por DNI se ejecutaba antes de restaurar los datos del POST. Se consulta después de restaurarlos y se vuelve a bloquear la identidad existente. Chrome reproduce el rechazo y verifica la recuperación del estado.
7. **Restricciones distintas entre HTML y servidor en logística.** Se alinearon patente, capacidad y número de despacho con la validación del servicio. Los identificadores del despacho también se validan antes de convertirlos.

## Verificaciones de esta iteración

- Se agregaron 30 casos parametrizados y de integración en `tests/test_depuracion_campos.py`, incluyendo una matriz de 51 solicitudes inválidas al cotizador.
- Se extendió el recorrido de Chrome de recepción para comprobar una búsqueda por DNI que responde tarde y el bloqueo del cliente tras un POST rechazado.
- El caso de efectivo entregado superior al precio confirma que el ingreso es el precio y que el efectivo físico suma solamente ese ingreso al fondo inicial. No se reprodujo una suma indebida del vuelto en ese recorrido.
- Recepción, rutas, reparto, retorno a central y dispositivo compartido pasaron sus recorridos de navegador locales. La emulación no sustituye un teléfono físico.

La batería completa terminó con **556 pruebas aprobadas, 1 omitida y 1 advertencia**, en 318,59 segundos. Se ejecutó con `py -m pytest -q -o faulthandler_timeout=60`, usando la configuración aislada descrita arriba y las rutas explícitas de Chrome y Playwright. La advertencia pertenece a ReportLab por el uso de `ast.NameConstant`, deprecado en Python 3.13. La verificación de enlaces simbólicos en Linux sigue pendiente. No se afirma ausencia total de errores por haber pasado las pruebas.

## Aplicación en el VPS

Esta iteración no añade migraciones ni dependencias. Desde una versión con las migraciones anteriores aplicadas, hacer respaldo, actualizar mediante `git pull --ff-only` y reiniciar `formopack`. Comprobar el estado del servicio y abrir un formulario nuevo para evitar usar HTML anterior al despliegue.

## Pendientes de aceptación externa

- Nuevo pago real con otra cuenta: confirmación automática, actualización de pantalla y un solo ingreso en caja.
- Teléfono físico: permisos GPS, firma, desconexión, suspensión, reapertura y sincronización sin duplicados.
- Prueba de enlaces simbólicos en Linux y restauración aislada de una copia externa reciente con evidencias privadas.
- Ensayo funcional del sitio publicado después de desplegar. Los resultados locales no prueban que el VPS tenga el mismo estado.
