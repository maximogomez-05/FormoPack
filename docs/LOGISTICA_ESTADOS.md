# Despacho, visitas y estados

Incremento del 26 de octubre de 2026. Reglas encapsuladas en `EstadoEnvio` y
`OperacionesLogisticas`; los controladores delegan las escrituras a ese servicio.

## Comportamiento implementado

- Administración crea despachos. Recepción puede registrar el ingreso a planta,
  pero no asignar flota, declarar siniestros ni resolver entregas manualmente.
- Se admiten envíos recibidos/en planta sin asignación actual y reintentos tras
  uno o dos fallos. La ruta anterior debe estar cerrada antes de reprogramar.
- La selección se valida nuevamente en servidor: cuenta activa, chofer correcto,
  vehículo disponible, envíos distintos, bultos con peso y capacidad por kg.
- Un despacho reserva el vehículo; el inicio explícito del chofer registra
  `fecha_inicio`, pasa sus visitas pendientes a `en_ruta` y habilita el GPS.
  Repetir el inicio no duplica eventos. Un siniestro previo no se reactiva.
- Se bloquean recursos durante la transacción. Índices únicos impiden dos rutas
  abiertas para el mismo chofer o vehículo incluso fuera de la aplicación.
- Una visita admite un solo resultado. Tras un fallo se conserva su asignación
  histórica y se libera el puntero de ruta actual para una futura reprogramación.
  Tres visitas fallidas bloquean un cuarto intento domiciliario.
- La entrega exige DNI válido y la firma según la validación existente.
  La validación profunda del contenido de firma/foto sigue pendiente.
- El formulario administrativo no permite fabricar entregas, poner un paquete
  en ruta sin inicio, ni reabrir estados terminales. Registra usuario, fecha,
  ubicación y observación. Las excepciones resuelven también la visita asignada.
- La última visita resuelta cierra la hoja y libera recursos en la misma
  transacción. Un reenvío de una petición antigua no libera un vehículo que
  ya tenga otro despacho. Los correos se solicitan después del commit.
- Consultas históricas y liquidaciones usan la asignación por visita: un
  reintento posterior no elimina al paquete de la hoja anterior ni cambia su
  resultado histórico. Los importes siguen siendo valor transportado; no
  representan una rendición de dinero cobrado por el chofer.
- Errores de persistencia se presentan sin SQL en pantalla. Si Leaflet no carga,
  logística muestra un aviso y conserva los formularios y las tablas utilizables.

## Significado del cierre

Una **visita resuelta** puede ser entregada, fallida o cerrada por una excepción.
Una **encomienda finalizada** está entregada, devuelta o siniestrada. Un fallo no
finaliza la encomienda, aunque sí termina esa visita dentro de la hoja.
El cierre operativo utiliza las resoluciones de las visitas, para que una ruta
con ausentes pueda finalizar sin inventar una entrega ni bloquear indefinidamente
el vehículo. Esta distinción debe incorporarse a la redacción de RF 6.1 y a sus
diagramas; no se declara equivalencia literal con la formulación original.

## Migración 009 y actualización local

Agrega `hojas_ruta_envios` (PK hoja/envío, resolución y fecha), inicio de ruta,
actor del historial e índices únicos mediante columnas generadas para recursos
activos. Recupera asociaciones desde el puntero actual y los intentos existentes.
No puede recuperar asignaciones antiguas que no dejaron ninguna de esas evidencias.
El inicio histórico inferido desde un intento es una aproximación, no una hora
de salida verificada. El script permite reejecución.

Antes de modificar el esquema, el gestor rechaza recursos con varias rutas
abiertas. La instalación local tenía rutas 1 y 3 abiertas con el mismo chofer
y vehículo. La ruta 3 tenía su único envío entregado: se comprobó nuevamente
bajo bloqueo y se cerró usando su evento de entrega del 07/10/2026 00:18:55.
Se conservaron la ruta 1 y el estado del vehículo, sin reabrir ni reasignar envíos.

Respaldo previo fuera del repositorio:
`C:\Users\maxig\.codex\backups\formopack\logistica-20261026-011432.sql`.
Se restauró en una base aleatoria de MariaDB aislada y se cotejaron los conteos
de las 20 tablas antes de aplicar la corrección y la migración 009.

## Validación reproducible

`tests/test_logistica_segura.py` usa MariaDB aislada con puerto explícito;
comprueba carreras por chofer, vehículo y envío, visitas concurrentes,
rollback por error SQL, permisos, capacidad, tres fallos, duplicación de visitas,
inicio repetido, bloqueo por mantenimiento, siniestro parcial, migración repetida
y rechazo de conflictos anteriores a la migración.
`tests/test_logistica_navegador.py` recorre despacho → inicio → fallo → nueva
ruta → entrega en Chrome y verifica el panel a 390 px. Usa las variables de
Node/Playwright documentadas para recepción. Los servicios externos están simulados.

Resultado: 346 pruebas de la selección segura acumulada aprobadas, dos antiguas
deseleccionadas. Después se agregaron dos casos (preflight de migración y
liquidación histórica) y se verificaron 40 pruebas de logística/páginas,
incluido Chrome y la corrección de avisos ocultos: 348 casos distintos aprobados.
No equivale a ejecutar toda la suite antigua ni a certificar todos los RF.
También se comprobaron dashboard, logística, liquidaciones, caja y chofer con
la base local actualizada: HTTP 200 sin errores de persistencia registrados.

## Pendientes y diagramas

Quedan retiro en sucursal con identidad/evidencia, devolución física y seguro;
control profundo de POD, coordenadas y cola offline con identidad persistente;
cobro en destino del RF 5.2 (pendiente de resolver con el alcance académico),
control de volumen si se conserva esa promesa, pruebas móviles reales y despliegue.
El orden por kilómetros existente no es un optimizador vial de múltiples paradas.

Al editar los diagramas: agregar la entidad de asignación histórica y sus
cardinalidades, `fecha_inicio`, actor e índices; incluir las clases de estados y
operaciones; representar reserva → inicio → visita → cierre, reprogramación y
custodia; retirar cambios manuales que eluden evidencia y cobros del chofer no
implementados. Los originales gráficos no se modificaron.
