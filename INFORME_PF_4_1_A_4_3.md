# Informe general de FormoPack

**Fecha:** 2026-09-02  
**Proyecto:** FormoPack Express  
**Alcance:** analisis del codigo, puesta en marcha, cambios de RF 3.0 a RF 3.3 y comparacion con diagramas.

Para una explicacion completa de los tipos de diagramas UML, sus elementos, relaciones y criterios de uso, consultar [INFORME_UML.md](INFORME_UML.md).

## 1. Resumen ejecutivo

FormoPack Express es una aplicacion web Flask para gestionar recepcion, cotizacion, clientes, envios, pagos, caja, tracking y logistica. Utiliza MySQL como base de datos y una organizacion modular cercana al patron MVC:

- `app/models`: entidades del dominio.
- `app/controllers`: logica de negocio y acceso coordinado a datos.
- `app/services`: servicios reutilizables, como cotizacion y ruteo.
- `web/routes`: rutas HTTP y permisos.
- `web/templates`: interfaz visual.
- `scripts`: inicializacion de la base y usuarios de prueba.

La version actual es funcional para los modulos de usuarios, recepcion, cotizacion, pagos basicos, caja, tracking y logistica. Los diagramas representan ademas funcionalidades planificadas que todavia no estan implementadas.

## 2. Como se ejecuta el proyecto

El punto de entrada web es `run.py`. `main.py` se utiliza para pruebas y no es el arranque principal del servidor.

Requisitos:

- Python 3.10 o superior.
- MySQL Server 8.0 o superior.
- Dependencias de `requirements.txt`.
- Archivo `.env` dentro de la carpeta `FormoPack`.

Configuracion minima de `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=formopack_db
DB_USER=root
DB_PASSWORD=CONTRASENA_DE_MYSQL
APP_DEBUG=false
SECRET_KEY=secret-key
```

Pasos en Windows:

```powershell
cd "C:\Users\maxim\OneDrive\Escritorio\Paqueteria\FormoPack"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\crear_usuario_prueba.py
.\.venv\Scripts\python.exe run.py
```

La base se inicializa ejecutando `scripts/init_database.sql` desde MySQL Workbench. El usuario de MySQL y el usuario de FormoPack son diferentes: la contrasena de MySQL se usa en `.env`; `admin123`, `recep456` y `chofer789` son contrasenas de la aplicacion.

URL principal:

```text
http://localhost:5000/login
```

Usuarios de prueba:

| Rol | Correo | Contrasena |
|---|---|---|
| Administrador | `admin@formopack.com` | `admin123` |
| Recepcionista | `recepcion@formopack.com` | `recep456` |
| Chofer | `chofer@formopack.com` | `chofer789` |

## 3. Requerimientos funcionales observados

### RF 1: usuarios y roles

Implementado:

- Inicio y cierre de sesion.
- Contraseñas almacenadas con bcrypt.
- Control de acceso por rol.
- Roles administrador, recepcionista y chofer.

Se comprueba iniciando sesion con cada usuario y verificando las opciones visibles.

### RF 2: recepcion y facturacion

Implementado de forma parcial o basica:

- Alta y consulta de clientes.
- Cotizacion por localidad, distancia y peso.
- Peso volumetrico.
- Regla de descuento multibulto.
- Recargo por manejo fragil.
- Seguro y valor declarado.
- Alta de envio y bultos.
- Cobro efectivo o digital como modalidad registrada.
- Apertura y cierre de caja.
- Generacion de comprobante interno PDF.

Pendiente o limitado:

- No hay integracion real con MercadoPago.
- El QR es una representacion local, no una confirmacion de un proveedor externo.
- El comprobante interno no es una factura fiscal.

### RF 3.0: logistica y despacho

Implementado en la ruta `/admin/logistica`:

- Resumen de entregas pendientes.
- Distancia total estimada.
- Cantidad de vehiculos.
- Cantidad de despachos activos.
- Visualizacion de flota, envios y hojas de ruta.

### RF 3.1: gestion de vehiculos

Se agrego una gestion persistente en MySQL:

- Modelo `Vehiculo`.
- Tabla `vehiculos`.
- Registro desde la interfaz de Logistica.
- Validacion de patente y capacidad mayor que cero.
- Estados `disponible`, `en_ruta`, `mantenimiento` y `fuera_de_servicio`.
- Visualizacion de disponibilidad.
- Prevencion de duplicados mediante la restriccion unica de patente.

### RF 3.2: hojas de ruta

Se agrego un flujo persistente para crear despachos:

- Seleccion de chofer activo.
- Seleccion de vehiculo disponible.
- Seleccion de uno o mas envios pendientes.
- Validacion de que los envios esten en estado `recibido` y no tengan despacho.
- Validacion de capacidad total del vehiculo.
- Registro en `hojas_de_ruta`.
- Asignacion de los envios mediante `envios.id_hoja_ruta`.
- Cambio de estado de los envios a `en_planta`.
- Cambio de estado del vehiculo a `en_ruta`.
- Visualizacion de hojas activas con chofer, vehiculo, cantidad y distancia.
- Rollback de la transaccion ante errores de validacion o SQL.

### RF 3.3: ruteo por kilometraje

Implementado:

- Consulta de envios recibidos y sin hoja de ruta.
- Obtencion de la distancia desde `localidades.distancia_km`.
- Ordenamiento de entregas de menor a mayor distancia.
- Calculo del recorrido total.
- Ordenamiento de los envios dentro de la hoja de ruta.

Se comprueba creando envios destinados a localidades con diferentes distancias y observando el orden en Logistica.

### RF 4: aplicacion movil del chofer

No implementado completamente:

- La vista del chofer es un placeholder.
- No hay PWA terminada.
- No hay foto, firma, GPS ni prueba de entrega operativa.
- RF 4.3 incorpora una cola local para entregas y sincronizacion al recuperar Internet; no cubre aun toda la operacion sin conexion.
- No hay notificaciones por WhatsApp.

### RF 5: tracking y dashboards

Implementado parcialmente:

- Dashboard administrativo con metricas basicas.
- Tracking publico por numero de guia.
- Timeline basado en `historial_estados`.

Pendiente:

- Metricas gerenciales avanzadas.
- Notificaciones automaticas.
- Integracion completa con la operacion del chofer.

## 4. Cambios realizados para RF 3.0 a RF 3.3

### Archivos creados previamente

- `app/models/vehiculo.py`: entidad de vehiculo y sus validaciones.
- `app/models/hoja_ruta.py`: entidad de hoja de ruta y ordenamiento de envios.
- `app/services/ruteo.py`: servicio de ordenamiento y calculo de distancias.
- `app/controllers/logistica_controller.py`: acceso a datos y operaciones de flota, despachos y ruteo.
- `web/templates/admin/logistica.html`: pantalla de logistica.
- `INFORME_RF_3_0_A_3_3.md`: informe especifico de la primera implementacion.

### Archivos modificados

- `web/app.py`: correccion del import de `request` usado por las cabeceras de seguridad.
- `web/routes/admin.py`: ruta de logistica, listado de choferes, registro de vehiculos y creacion de hojas de ruta.
- `web/templates/admin/logistica.html`: formularios visibles para registrar vehiculos y crear despachos.
- `app/controllers/logistica_controller.py`: validaciones de capacidad, vehiculo disponible, chofer activo y transacciones.
- `scripts/init_database.sql`: esquema y datos base de las tablas utilizadas por logistica.

## 5. Validaciones realizadas

- La conexion de MySQL fue probada correctamente desde MySQL Workbench.
- Se ejecuto `init_database.sql`; las advertencias mostradas fueron avisos de compatibilidad de MySQL, no errores que impidieran crear las tablas.
- Se cargaron los tres usuarios de prueba correctamente.
- La pagina de login respondio correctamente.
- La pagina `/admin/logistica` respondio con HTTP 200.
- Los modulos Python modificados pasaron `py_compile` sin errores.
- Se comprobo el flujo de login despues de configurar `.env` y crear la base.

## 6. Comparacion con los diagramas

### Diagrama de clases

Coincide con el proyecto en:

- `Cliente`, `Envio`, `Bulto`, `Seguro`, `Vehiculo`, `HojaRuta`.
- `Usuario` y sus roles.
- `HistorialEstado`, `TurnoCaja` y `Pago`.
- `Cotizador` y `ServicioRuteo`.
- Relaciones principales entre clientes, envios, bultos, localidades, pagos, vehiculos y hojas de ruta.

No coincide completamente porque el diagrama tambien incluye clases no implementadas:

- `Factura`.
- `EntregaFallida` y `PruebaDeEntrega` como modelos completos.
- `GestionSincronizacionOffline`.
- `ServicioNotification`.
- `ControladorInventario`.
- Una integracion externa real de `PagoDigital`.

`GeneradorDocumentos` tampoco coincide literalmente: el proyecto utiliza `GeneradorGuia`, `ComprobanteInterno` y el generador PDF de `web/utils`.

### Diagrama de casos de uso

Coincide en login, clientes, cotizacion, cobro basico, caja, tracking, vehiculos y hojas de ruta.

Representa funcionalidades futuras que no pueden probarse aun:

- Aplicacion movil del chofer.
- Firma, foto y GPS.
- Entrega fallida.
- WhatsApp.
- Modo offline.
- MercadoPago real.
- Inventario.
- Facturacion fiscal.

### Diagrama de secuencia

Coincide con el flujo actual hasta:

1. Cotizar.
2. Crear envio y bultos.
3. Registrar pago.
4. Emitir comprobante.
5. Armar despacho.
6. Consultar tracking.

No coincide con la parte de confirmacion externa de MercadoPago, entrega movil, firma, foto, GPS, notificacion y sincronizacion offline porque esas funciones aun no existen.

### Diagrama entidad-relacion

Es el diagrama que mejor coincide con `scripts/init_database.sql`. Contiene las tablas principales:

- `usuarios`.
- `clientes`.
- `localidades`.
- `seguros`.
- `vehiculos`.
- `hojas_de_ruta`.
- `envios`.
- `bultos`.
- `historial_estados`.
- `turnos_caja`.
- `pagos`.
- `comprobantes_internos`.
- `intentos_entrega`.

Le faltan tablas para notificaciones, inventario, facturas fiscales, fotos, firmas, GPS y sincronizacion offline si esas funcionalidades se consideran parte de la version actual.

## 7. Inconsistencias tecnicas importantes

- El diagrama muestra una solucion completa, pero el codigo actual es una version parcial.
- El pago digital no confirma una operacion real con MercadoPago.
- El comprobante interno no reemplaza una factura fiscal.
- `intentos_entrega` existe en SQL, pero no tiene aun un flujo completo de entrega.
- La pantalla de Logistica inicialmente solo mostraba informacion; ahora tambien permite registrar vehiculos y crear hojas de ruta.
- Los diagramas deberian distinguir entre funcionalidades implementadas y funcionalidades futuras.

## 8. Como demostrar RF 3.1, RF 3.2 y RF 3.3

1. Entrar como administrador.
2. Abrir **Logistica**.
3. En **Registrar vehiculo**, ingresar una patente, por ejemplo `AA123BB`, y capacidad `1000` kg.
4. Presionar **Guardar vehiculo** y verificar que aparezca en la flota.
5. En **Crear hoja de ruta**, elegir `DESP-001`, un chofer, el vehiculo registrado y el envio pendiente.
6. Presionar **Crear despacho**.
7. Verificar que la hoja aparezca en **Hojas de ruta activas**.
8. Verificar que el vehiculo figure `en_ruta` y el envio `en_planta`.
9. Para RF 3.3, crear varios envios con localidades diferentes y comprobar que la tabla se ordene por kilometraje ascendente.

## 9. Conclusion para presentar el proyecto

Los diagramas son validos como modelo general y vision futura del sistema, pero no deben presentarse como una fotografia exacta de toda la implementacion actual.

La forma correcta de explicarlo es:

> Los diagramas representan la vision completa de FormoPack. La version implementada cubre usuarios, recepcion, cotizacion, pagos basicos, caja, tracking y logistica, incluyendo gestion de vehiculos, hojas de ruta y ruteo por kilometraje. Tambien incorpora un modulo movil instalable para el chofer, prueba de entrega con GPS, foto y firma, y sincronizacion offline de entregas. Notificaciones, inventario, facturacion fiscal y la integracion real con MercadoPago quedan como funcionalidades posteriores.

Con esa aclaracion, el codigo y los diagramas quedan alineados como arquitectura por etapas y se evita afirmar que una funcionalidad futura ya esta operativa.

## 10

### Limitaciones que permanecen

- No se implementaron notificaciones por WhatsApp, email o SMS.
- No se implemento MercadoPago real ni webhook.
- No se implemento facturacion fiscal.
- No se implemento inventario.
- El primer acceso al panel debe hacerse online para instalar el service worker y cargar la vista.
- El inicio de ruta requiere conexion; la cola offline se aplica a los resultados de entrega.
- La sincronizacion depende del almacenamiento local del navegador y aun no tiene resolucion avanzada de conflictos.
