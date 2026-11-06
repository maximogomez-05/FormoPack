# Preparación de la demostración

Desde una sesión SSH del VPS, con el usuario formopack y la migración 014 aplicada, ejecutar scripts/preparar_demostracion.py. El programa solicita el ingreso de un administrador existente, sin modificar su sesión web. Con --cuenta NOMBRE CORREO se agregan administradores activos con cambio obligatorio de contraseña. Una cuenta ya existente conserva su contraseña, rol y estado.

La contraseña provisoria se ingresa de forma oculta dos veces. Se valida con la misma política de la aplicación, ocho caracteres como mínimo, letras y números y hasta 72 bytes UTF-8. Al primer ingreso deben elegir una contraseña diferente. Los correos y contraseñas personales se proporcionan al ejecutar y no quedan almacenados en este script.

Con --datos-demo se agregan 14 envíos de clientes identificados como Demo, sin correo de contacto, con documentación de recepción y pendientes de cobro. Las fechas de creación y recepción simulan los últimos siete días, mientras las guías se generan en la fecha de ejecución. La actividad histórica es ficticia. Los envíos se reconocen también por su observación DEMO en el historial y su dirección ficticia. No se crean pagos, caja, rutas ni entregas. Los importes cotizados aumentan el valor de envíos registrados, mientras la recaudación depende de los cobros confirmados.

La carga conserva los registros anteriores. Se puede repetir con el mismo administrador y solo crea los ejemplos faltantes. Si un DNI reservado para la muestra coincide con un cliente diferente, se revierte el lote completo. Las altas de cuentas son independientes del lote operativo. Si una etapa falla, las cuentas ya creadas se conservan.

El script antiguo seed_demo.py vacía tablas y restablece cuentas de prueba. Para esta carga en el sitio publicado se utiliza exclusivamente preparar_demostracion.py.

Verificación local con MariaDB aislada. Se comprobaron preservación de un envío anterior, repetición sin duplicación, reversión del lote ante conflicto, ausencia de correos y pagos, rechazo de un chofer y cambio obligatorio de clave. La ejecución sobre el VPS se realiza con sus datos y credenciales de acceso.
