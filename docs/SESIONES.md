# Sesiones del personal

Cada ingreso web exitoso incrementa la versión persistente de la cuenta y regenera el identificador de sesión. El ingreso más reciente invalida el anterior, incluso entre procesos del servidor. Las pestañas que comparten la misma cookie comparten una sesión.

Administración y recepción vencen a los 30 minutos sin solicitudes de actividad. Choferes vencen a las 8 horas sin actividad. Todas las sesiones tienen un límite absoluto de 12 horas desde su inicio. Los sondeos JSON y la consulta de vigencia no renuevan la actividad. Cambiar de pantalla mediante una solicitud normal renueva la inactividad. Mantener un formulario abierto sin enviarlo no renueva el plazo.

El servidor valida los plazos antes de consultar los permisos vigentes de la cuenta. Una sesión sin fechas de inicio y actividad requiere autenticación nuevamente. El cierre revoca la versión y elimina el identificador anterior del almacén. La regeneración posterior al cambio de contraseña inicial también conserva la política de sesión única.

El historial del navegador puede volver a pantallas mientras la sesión continúe vigente. Las páginas restauradas desde BFCache consultan al servidor y se recargan. El panel consulta su vigencia cada minuto y al recuperar visibilidad. El servidor controla cada operación aunque la página permaneciera abierta.

El trabajo offline del chofer conserva sus registros locales. Al sincronizar se exige una sesión vigente. La comprobación de vigencia de una pestaña necesita conexión.

## Verificación

Se ejecutaron 86 pruebas de vigencia, primer acceso, páginas, permisos y seguridad HTTP con persistencia aislada. En Chrome se verificaron historial con sesión vigente, invalidación por segundo ingreso y cierre seguido de navegación hacia atrás. Los servicios externos se simularon.

## Actualización del VPS

Respaldar, actualizar el repositorio y reiniciar el servicio. No requiere migraciones SQL. Las sesiones previas al despliegue deben autenticarse nuevamente.
