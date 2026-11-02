# DICCIONARIO DE DATOS — DIAGRAMA DE CLASES UML
## Sistema FormoPack Express — Gestión Logística, Distribución y Facturación
**Autores:** Máximo Gómez, Máximo Gavilán, Julián González  
**Versión:** 3.5 Enterprise  
**Fecha:** Octubre 2026  

---

## 1. INTRODUCCIÓN Y CONVENCIONES

El presente **Diccionario de Datos del Diagrama de Clases** describe de manera formal y detallada cada una de las entidades de software, clases de dominio, clases especializadas y componentes de servicio representados en el **Diagrama de Clases UML** del sistema FormoPack Express.

### Convenciones de Nomenclatura y Visibilidad
- **Visibilidad:**
  - `-` : Privado (*Private*). Accesible únicamente dentro de la propia clase (encapsulamiento).
  - `+` : Público (*Public*). Accesible por cualquier componente del sistema.
  - `#` : Protegido (*Protected*). Accesible por la clase y sus subclases derivadas.
- **Tipos de Datos:**
  - `int`: Número entero de 32 bits.
  - `float`: Número decimal de precisión flotante (representa importes monetarios, pesos en kg, distancias en km).
  - `String`: Cadena de texto alfanumérica.
  - `boolean`: Valor lógico booleano (`true` o `false`).
  - `DateTime`: Marca temporal que almacena fecha y hora exacta.
  - `ArchivoPDF`: Flujo binario o archivo descargable en formato PDF.
  - `void`: Operación sin valor de retorno.

---

## 2. SUBSISTEMA DE SEGURIDAD, USUARIOS Y AUTENTICACIÓN

```
                        ┌─────────────┐
                        │   Usuario   │
                        └──────┬──────┘
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
     ┌───────────────┐   ┌───────────┐   ┌───────────────┐
     │ Administrador │   │  Chofer   │   │ Recepcionista │
     └───────────────┘   └───────────┘   └───────────────┘
```

### 2.1 Clase: `Usuario` (Clase Base)
- **Descripción:** Modela la entidad base del personal operativo de la empresa con credenciales para acceder y operar el sistema web. Implementa el control de acceso basado en roles (RBAC).
- **Paquete / Módulo:** `app.models.usuario`
- **Relaciones:**
  - *Generalización (Herencia):* Es la superclase de `Administrador`, `Chofer` y `Recepcionista`.
  - *Asociación:* Se relaciona con `RecuperacionContrasena` (1 a 0..*).
  - *Asociación:* Se relaciona con `ChatSoporte` (1 a 0..*) en calidad de operador asignado ("Atiende").

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idUsuario` | `int` | Identificador único irrepetible del usuario en el sistema (Clave primaria). |
| `-` | `nombre` | `String` | Nombre y apellido completo del personal (Mínimo 3, máximo 100 caracteres). |
| `-` | `email` | `String` | Correo electrónico corporativo único usado como cuenta de acceso (Login). |
| `-` | `credencialesHash` | `String` | Hash criptográfico seguro de la contraseña generado mediante algoritmo Bcrypt. |
| `-` | `tipoUsuario` | `String` | Rol asignado en el sistema (`'administrador'`, `'recepcionista'`, `'chofer'`). |
| `-` | `activo` | `boolean` | Indicador de baja lógica. Si es `true`, el usuario puede iniciar sesión; si es `false`, se bloquea el acceso. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `autenticar(clave: String)` | `boolean` | Valida la contraseña ingresada en texto plano contra el hash Bcrypt almacenado. Retorna `true` si es correcta. |

---

### 2.2 Clase: `Administrador` (Subclase de `Usuario`)
- **Descripción:** Representa al personal de gerencia y administración logística con privilegios máximos en el sistema.
- **Herencia:** Especialización de `Usuario`.

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `autorizarSiniestro()` | `void` | Permite cambiar de forma auditada el estado de un envío a 'siniestro' o forzar excepciones operativas. |
| `+` | `configurarSeguro()` | `void` | Ajusta las coberturas bases y los porcentajes por excedente de las pólizas de seguro. |
| `+` | `gestionarUsuarios()` | `void` | Realiza el alta, modificación de rol y activación/desactivación del personal. |

---

### 2.3 Clase: `Chofer` (Subclase de `Usuario`)
- **Descripción:** Representa al repartidor responsable de la conducción de las unidades vehiculares y de la distribución física de última milla.
- **Herencia:** Especialización de `Usuario`.
- **Relaciones:**
  - *Asociación:* Conduce y ejecuta instancias de `HojaDeRuta` (1 a 0..*).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `nroLicencia` | `String` | Número de registro o licencia nacional de conducir habilitada. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `registrarEntrega(idEnvio, dni, firma)` | `boolean` | Registra una Prueba de Entrega (POD) exitosa, almacenando DNI del receptor y firma táctil. |
| `+` | `reportarVisitaFallida(idEnvio, motivo)` | `boolean` | Asienta una visita infructuosa tipificando el motivo (destinatario ausente, domicilio incorrecto, etc.). |
| `+` | `transmitirUbicacionGPS(lat, lng, precision)` | `void` | Envía las coordenadas satelitales del dispositivo móvil al centro de despacho logístico. |

---

### 2.4 Clase: `Recepcionista` (Subclase de `Usuario`)
- **Descripción:** Modela al operador de sucursal encargado de la atención al cliente en mostrador, tasación de encomiendas y cobro.
- **Herencia:** Especialización de `Usuario`.

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `abrirTurnoCaja(saldoInicial: float)` | `TurnoCaja` | Inicia una nueva sesión contable de caja con el monto inicial en efectivo declarado. |
| `+` | `cotizarEnvio(bultos, localidad)` | `float` | Calcula la cotización previa de una encomienda en base al aforo, seguro y descuentos multibulto. |

---

### 2.5 Clase: `RecuperacionContrasena`
- **Descripción:** Gestiona los códigos temporales de un solo uso (OTP) para el restablecimiento seguro de claves de acceso por correo.
- **Paquete / Módulo:** `app.controllers.auth_controller`
- **Relaciones:**
  - *Asociación:* Pertenece a un `Usuario` (0..* a 1).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idRecuperacion` | `int` | Identificador único del registro de solicitud de recuperación (Clave primaria). |
| `-` | `codigo` | `String` | Código numérico aleatorio de 6 dígitos enviado a la casilla del usuario. |
| `-` | `expiraEn` | `DateTime` | Marca temporal que fija el límite de validez del código (15 minutos desde su emisión). |
| `-` | `utilizado` | `boolean` | Flag de consumo. Evita que un código ya usado pueda volver a ser presentado (`true` = invalidado). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `validarCodigo(codigoIngresado: String)` | `boolean` | Verifica que el código coincida, pertenezca a la cuenta, no esté vencido y no haya sido utilizado. |
| `+` | `marcarUtilizado()` | `void` | Actualiza el atributo `utilizado` a `true` tras concretarse el cambio de clave. |

---

## 3. SUBSISTEMA DE RECEPCIÓN, ENCOMIENDAS Y TARIFACIÓN

```
 ┌─────────┐ 1         Remitente 0..* ┌───────┐ 1..*       1 ┌───────┐
 │ Cliente ├──────────────────────────┤ Envio ├───────────────┤ Bulto │
 └─────────┘ 1       Destinatario 0..* └───┬───┘               └───────┘
                                           │ 1
                                           │ Composición
                                           ├───────────────► 0..* HistorialEstado
                                           ├───────────────► 0..* ComprobanteInterno
                                           └───────────────► 0..* IntentoEntrega
```

### 3.1 Clase: `Envio` (Entidad Central)
- **Descripción:** Representa el contrato y paquete logístico registrado en el sistema. Centraliza los bultos, clientes involucrados, costos y el ciclo de vida de estados.
- **Paquete / Módulo:** `app.models.envio`
- **Relaciones:**
  - *Asociación:* Se vincula con `Cliente` como Remitente (0..* a 1) y como Destinatario (0..* a 1).
  - *Asociación:* Destinado a una `Localidad` (0..* a 1).
  - *Asociación:* Vinculado opcionalmente a una póliza de `Seguro` (0..* a 1).
  - *Asociación:* Asignado a una `HojaDeRuta` para su despacho (0..* a 1).
  - *Asociación:* Posee un único `Pago` asociado (1 a 1).
  - *Composición:* Contiene uno o más `Bulto` (1 a 1..*).
  - *Composición:* Contiene su trazabilidad histórica en `HistorialEstado` (1 a 0..*).
  - *Composición:* Posee registros de `ComprobanteInterno` (1 a 0..*).
  - *Composición:* Registra intentos de reparto en `IntentoEntrega` (1 a 0..*).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idEnvio` | `int` | Clave primaria única del envío. |
| `-` | `nroGuia` | `String` | Código identificador público irrepetible visible en remitos y tracking (Ej: `'FP-84920182'`). |
| `-` | `valorDeclarado` | `float` | Monto monetario declarado por el cliente sobre el contenido del paquete. |
| `-` | `modalidadPago` | `String` | Método acordado para el cobro (`'efectivo'`, `'digital'`, `'cuenta_corriente'`). |
| `-` | `costoTotal` | `float` | Importe final total liquidado por el envío (Flete + Seguro + Adicionales). |
| `-` | `estadoActual` | `String` | Estado operativo del envío (`'recibido'`, `'en_planta'`, `'en_ruta'`, `'entregado'`, `'fallido'`, `'devolucion'`, `'siniestro'`). |
| `-` | `direccionDestino` | `String` | Dirección física exacta donde debe entregarse la encomienda. |
| `-` | `esDevolucion` | `boolean` | Flag que indica si la carga está retornando a la sucursal de origen tras 3 visitas fallidas. |
| `-` | `fechaCreacion` | `DateTime` | Marca temporal del momento en que fue registrado en mostrador. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `agregarBulto(bulto: Bulto)` | `void` | Incorpora un nuevo bulto al envío y recalcula los totales de carga. |
| `+` | `actualizarEstado(nuevoEstado: String)` | `void` | Modifica el estado del envío y registra automáticamente el nuevo hito en el historial de auditoría. |

---

### 3.2 Clase: `Bulto`
- **Descripción:** Modela cada paquete o caja individual que compone un envío.
- **Paquete / Módulo:** `app.models.bulto`
- **Relaciones:**
  - *Composición:* Pertenece estrictamente a una instancia de `Envio` (1..* a 1).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idBulto` | `int` | Identificador único del bulto. |
| `-` | `pesoReal` | `float` | Peso físico real en kilogramos determinado mediante báscula. |
| `-` | `pesoVolumetrico` | `float` | Peso cúbico en kg calculado mediante fórmula estándar: `(Largo * Ancho * Alto) / 5000`. |
| `-` | `esFragil` | `boolean` | Si es `true`, aplica recargo tarifario del 10% y estampa etiqueta de manipulación cuidadosa. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `calcularAforo()` | `float` | Aplica la regla de aforo IATA: retorna el valor máximo entre `pesoReal` y `pesoVolumetrico`. |

---

### 3.3 Clase: `HistorialEstado`
- **Descripción:** Registra de manera secuencial e inalterable cada cambio de estado que experimenta el paquete a lo largo del tiempo (Timeline de Tracking).
- **Paquete / Módulo:** `app.models.historial_estado`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idHistorial` | `int` | Clave primaria del evento histórico. |
| `-` | `estado` | `String` | Nombre del estado asumido (`'recibido'`, `'en_planta'`, etc.). |
| `-` | `fechaHora` | `DateTime` | Momento exacto en que se produjo la transición de estado. |
| `-` | `ubicacion` | `String` | Localidad, depósito o coordenadas donde se suscitó el evento. |
| `-` | `observacion` | `String` | Detalle informativo, motivo de fallo o justificación de auditoría. |

---

### 3.4 Clase: `ComprobanteInterno`
- **Descripción:** Modela los comprobantes de recepción no fiscales emitidos por el sistema para respaldo del remitente.
- **Paquete / Módulo:** `app.models.comprobante_interno`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idComprobante` | `int` | Clave primaria del comprobante. |
| `-` | `nroComprobante` | `String` | Número correlativo único oficial (Ej: `'REC-2026-000142'`). |
| `-` | `tipoComprobante` | `String` | Tipo de documento emitido (`'recepcion'`, `'despacho'`). |
| `-` | `fechaEmision` | `DateTime` | Fecha y hora en que se emitió el documento. |

---

### 3.5 Clase: `IntentoEntrega`
- **Descripción:** Almacena la evidencia física y digital de cada visita que el chofer realiza en el domicilio del destinatario (POD - Proof of Delivery).
- **Paquete / Módulo:** `app.models.prueba_entrega`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idIntento` | `int` | Clave primaria del intento de entrega. |
| `-` | `fechaHora` | `DateTime` | Marca temporal de la visita en campo. |
| `-` | `coordenadasGps` | `String` | Coordenadas de latitud y longitud satelital obtenidas al momento del intento. |
| `-` | `tipoIntento` | `String` | Resultado de la visita (`'entregado'` o `'fallido'`). |
| `-` | `motivoFallo` | `String` | Causa en caso de no entrega (`'destinatario_ausente'`, `'domicilio_incorrecto'`, `'rechazo'`). |
| `-` | `dniReceptor` | `String` | Documento Nacional de Identidad de la persona que recibe la carga. |
| `-` | `firmaReceptor` | `String` | Firma ológrafa digitalizada en formato vectorial o Base64 capturada desde la pantalla táctil. |
| `-` | `fotoRemito` | `String` | Ruta al archivo fotográfico del remito firmado o paquete entregado. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `registrarFirmaDigital(base64: String)` | `void` | Valida y almacena el trazo de la firma electrónica capturado en el Canvas HTML5. |

---

### 3.6 Clase: `Cliente`
- **Descripción:** Representa a las personas físicas o empresas que participan como remitentes o destinatarios del servicio de encomiendas.
- **Paquete / Módulo:** `app.models.cliente`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idCliente` | `int` | Clave primaria del cliente. |
| `-` | `dni` | `String` | DNI o CUIT único del cliente (Sin puntos ni guiones, 7 a 15 dígitos). |
| `-` | `nombreCompleto` | `String` | Razón social o nombre y apellido completo. |
| `-` | `telefono` | `String` | Teléfono de contacto directo para avisos de entrega y WhatsApp. |
| `-` | `email` | `String` | Casilla electrónica para el envío de notificaciones automáticas de tracking. |

---

### 3.7 Clase: `Localidad`
- **Descripción:** Modela los destinos geográficos atendidos por la empresa dentro del corredor logístico provincial.
- **Paquete / Módulo:** `app.models.localidad`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idLocalidad` | `int` | Identificador único de la localidad. |
| `-` | `nombre` | `String` | Nombre de la ciudad o pueblo (Ej: `'Clorinda'`, `'Las Lomitas'`). |
| `-` | `distanciaKm` | `float` | Distancia en kilómetros medida desde la Sede Central Formosa (Base del ruteo). |

---

### 3.8 Clase: `Seguro`
- **Descripción:** Establece los parámetros de cobertura patrimonial sobre el valor declarado de las encomiendas transportadas.
- **Paquete / Módulo:** `app.models.seguro`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idSeguro` | `int` | Clave primaria de la póliza de seguro. |
| `-` | `coberturaEstandar` | `float` | Monto máximo cubierto por defecto sin recargo tarifario (Ej: `$ 50,000.00`). |
| `-` | `porcentajeExcedente` | `float` | Porcentaje de prima aplicable sobre el monto que exceda la cobertura estándar (Ej: `1.5%`). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `calcularCosto(valorDeclarado: float)` | `float` | Determina el costo del seguro evaluando si el valor declarado supera el umbral estándar. |

---

## 4. SUBSISTEMA DE LOGÍSTICA, FLOTA Y TELEMETRÍA

```
 ┌──────────┐ 1           0..* ┌─────────────┐ 1       0..1 ┌────────────────────┐
 │ Vehiculo ├──────────────────┤ HojaDeRuta  ├──────────────┤ UbicacionHojaRuta  │
 └──────────┘                  └──────┬──────┘ Composición  └────────────────────┘
                                      │ 1
                                      │ Asociación
                                      ▼ 0..*
                                  ┌───────┐
                                  │ Envio │
                                  └───────┘
```

### 4.1 Clase: `Vehiculo`
- **Descripción:** Representa las unidades motrices (camionetas, furgones, camiones) que componen la flota de transporte de la empresa.
- **Paquete / Módulo:** `app.models.vehiculo`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idVehiculo` | `int` | Identificador único del vehículo en la flota. |
| `-` | `patente` | `String` | Matrícula o dominio del automotor (Formato único alfanumérico de 5 a 10 caracteres). |
| `-` | `capacidadKg` | `float` | Capacidad máxima de carga útil habilitada en kilogramos. |
| `-` | `estado` | `String` | Estado operativo de la unidad (`'disponible'`, `'en_ruta'`, `'mantenimiento'`, `'fuera_de_servicio'`). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `verificarCapacidadDisponible()` | `float` | Calcula el remanente de carga en kilogramos comparando su capacidad contra la carga estibada actual. |

---

### 4.2 Clase: `HojaDeRuta` (Manifiesto de Despacho)
- **Descripción:** Agrupa un conjunto de envíos asignados a un chofer y un vehículo para su distribución geográfica en un recorrido planificado.
- **Paquete / Módulo:** `app.models.hoja_ruta`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idHojaRuta` | `int` | Clave primaria de la hoja de ruta. |
| `-` | `nroDespacho` | `String` | Código identificador del despacho (Ej: `'DESP-2026-0084'`). |
| `-` | `fechaEmision` | `DateTime` | Momento en que el administrador generó el despacho. |
| `-` | `fechaCierre` | `DateTime` | Momento exacto en que concluyeron todas las entregas y se dio por cerrada la ruta. |
| `-` | `estado` | `String` | Estado de la hoja (`'abierta'`, `'cerrada'`). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `agregarEnvio(envio: Envio)` | `void` | Asocia un envío validando previamente que la capacidad del móvil no sea superada. |
| `+` | `calcularRutaOptima()` | `list` | Ordena las paradas secuencialmente en función del kilometraje ascendente de las localidades. |
| `+` | `verificarCierreAutomatico()` | `boolean` | Comprueba si todos los paquetes asignados llegaron a un estado terminal (`entregado`/`fallido`). |
| `+` | `cerrarHojaRuta()` | `void` | Marca la hoja como `'cerrada'`, sella `fechaCierre` y conmuta el vehículo a `'disponible'`. |

---

### 4.3 Clase: `UbicacionHojaRuta`
- **Descripción:** Mantiene la última posición satelital GPS reportada en tiempo real por el dispositivo del chofer para una hoja de ruta abierta.
- **Paquete / Módulo:** Base de datos y telemetría de despacho.

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idHojaRuta` | `int` | Identificador de la hoja de ruta asociada (Clave primaria y foránea). |
| `-` | `idChofer` | `int` | Identificador del chofer que emite la señal satelital. |
| `-` | `latitud` | `float` | Coordenada geográfica de latitud en grados decimales (Precisión 7 decimales). |
| `-` | `longitud` | `float` | Coordenada geográfica de longitud en grados decimales. |
| `-` | `precisionM` | `float` | Radio de incertidumbre o margen de error del GPS expresado en metros. |
| `-` | `fechaActualizacion` | `DateTime` | Timestamp de la última telemetría transmitida. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `actualizarPosicion(lat: float, lng: float)` | `void` | Sobrescribe las coordenadas y refresca la marca temporal para alimentar el mapa interactivo Leaflet. |

---

## 5. SUBSISTEMA DE FINANZAS, PAGOS Y ARQUEO DE CAJA

```
                               ┌───────────┐
                               │   Pago    │
                               └─────┬─────┘
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
             ┌──────────────┐                 ┌─────────────┐
             │ PagoEfectivo │                 │ PagoDigital │
             └──────────────┘                 └─────────────┘
```

### 5.1 Clase: `Pago` (Clase Base)
- **Descripción:** Entidad financiera que modela el cobro registrado por la prestación del servicio de encomiendas.
- **Paquete / Módulo:** `app.models.pago`
- **Relaciones:**
  - *Generalización:* Superclase de `PagoEfectivo` y `PagoDigital`.
  - *Asociación:* Pertenece a un `TurnoCaja` abierto (0..* a 1).
  - *Asociación:* Vinculado de forma unívoca a un `Envio` (1 a 1).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idPago` | `int` | Clave primaria de la transacción de pago. |
| `-` | `idEnvio` | `int` | Clave foránea que referencia al envío cancelado. |
| `-` | `idTurno` | `int` | Referencia al turno de caja activo en el cual se recaudó el dinero. |
| `-` | `monto` | `float` | Importe monetario exacto del cobro. |
| `-` | `fecha` | `DateTime` | Fecha y hora en que se asentó el pago. |
| `-` | `tipoPago` | `String` | Modalidad de la transacción (`'efectivo'` o `'digital'`). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `procesarPago()` | `boolean` | Valida que el monto sea mayor a 0 y asienta la transacción en la sesión contable activa. |

---

### 5.2 Clase: `PagoEfectivo` (Subclase de `Pago`)
- **Descripción:** Especialización para cobros realizados en moneda de curso legal (billetes físicos en mostrador).
- **Herencia:** Especialización de `Pago`.

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `montoEntregado` | `float` | Cantidad de dinero físico entregada por el cliente para abonar la tarifa. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `calcularVuelto()` | `float` | Calcula la diferencia aritmética: `montoEntregado - monto` para reintegro en ventanilla. |

---

### 5.3 Clase: `PagoDigital` (Subclase de `Pago`)
- **Descripción:** Especialización para cobros por medios electrónicos, transferencias y pasarela de Mercado Pago mediante código QR.
- **Herencia:** Especialización de `Pago`.

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `transaccionQr` | `String` | Código identificador de la cadena o string dinámico codificado en el QR. |
| `-` | `billeteraVirtual` | `String` | Nombre de la entidad o aplicación emisora (`'MercadoPago'`, `'Transferencia'`). |
| `-` | `idTransaccionExt` | `String` | Identificador único devuelto por la API externa (`payment_id` de Mercado Pago). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `generarQrDinamico()` | `String` | Conecta con la pasarela para emitir la URL y generar la imagen del código QR de cobro. |

---

### 5.4 Clase: `TurnoCaja`
- **Descripción:** Modela la sesión de caja de un recepcionista para el control del efectivo en gaveta y la conciliación contable contra billeteras virtuales.
- **Paquete / Módulo:** `app.models.turno_caja`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idTurno` | `int` | Clave primaria de la sesión de caja. |
| `-` | `idRecepcionista` | `int` | Clave foránea del operador titular del turno. |
| `-` | `fechaApertura` | `DateTime` | Momento exacto de inicio del turno. |
| `-` | `fechaCierre` | `DateTime` | Momento de cierre definitivo y bloqueo contable del turno. |
| `-` | `saldoInicial` | `float` | Fondo fijo de apertura en billetes físicos. |
| `-` | `ingresosEfectivo` | `float` | Total acumulado de cobros recaudados en billetes físicos. |
| `-` | `ingresosDigitales` | `float` | Total acumulado acreditado por medios electrónicos (Mercado Pago). |
| `-` | `estadoCaja` | `String` | Estado del turno (`'abierto'`, `'cerrado'`). |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `registrarIngreso(monto: float, tipo: String)` | `void` | Suma el cobro al total acumulado correspondiente (`ingresosEfectivo` o `ingresosDigitales`). |
| `+` | `realizarArqueo()` | `float` | Calcula el total físico que debe existir en el cajón: `saldoInicial + ingresosEfectivo`. |

---

## 6. SUBSISTEMA DE SOPORTE AL CLIENTE Y CHAT EN VIVO

```
 ┌─────────────┐ 1               0..* ┌────────────────┐
 │ ChatSoporte ├──────────────────────┤ MensajeSoporte │
 └─────────────┘ Composición          └────────────────┘
```

### 6.1 Clase: `ChatSoporte`
- **Descripción:** Administra la sesión de diálogo y atención técnica iniciada por un cliente desde la interfaz pública de tracking.
- **Paquete / Módulo:** `app.controllers.soporte_controller`
- **Relaciones:**
  - *Composición:* Contiene las líneas de conversación en `MensajeSoporte` (1 a 0..*).
  - *Asociación:* Atendido de forma exclusiva por un `Usuario` operador (0..* a 1).

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idChat` | `int` | Clave primaria de la conversación de soporte. |
| `-` | `sessionId` | `String` | Token alfanumérico único (UUID4) asignado a la pestaña del navegador del cliente. |
| `-` | `clienteNombre` | `String` | Nombre manifestado por el consultante. |
| `-` | `clienteEmail` | `String` | Correo de contacto del cliente. |
| `-` | `nroGuia` | `String` | Número de envío sobre el cual se realiza la consulta técnica o reclamo. |
| `-` | `estado` | `String` | Estado de la sesión (`'sin_atender'`, `'en_progreso'`). |
| `-` | `idUsuarioAtendiendo` | `int` | ID del operador de mostrador o administrador asignado en exclusividad. |

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `asignarOperador(idUsuario: int)` | `void` | Bloquea la conversación para que ningún otro operador interfiera y conmuta a `'en_progreso'`. |
| `+` | `finalizarChat()` | `void` | Cierra la sesión de atención y desencadena la purga de los mensajes temporales. |

---

### 6.2 Clase: `MensajeSoporte`
- **Descripción:** Representa cada mensaje individual intercambiado en tiempo real entre el cliente y el operador dentro de la sala de soporte.
- **Paquete / Módulo:** `app.controllers.soporte_controller`

#### Atributos
| Visibilidad | Nombre | Tipo | Descripción y Reglas de Negocio |
|:---:|---|:---:|---|
| `-` | `idMensaje` | `int` | Clave primaria del mensaje. |
| `-` | `remitenteTipo` | `String` | Origen del mensaje: `'cliente'` o `'soporte'`. |
| `-` | `remitenteNombre` | `String` | Nombre visible del emisor en la burbuja de chat. |
| `-` | `mensaje` | `String` | Texto íntegro transmitido en la conversación. |
| `-` | `fechaEnvio` | `DateTime` | Hora y minuto exacto de transmisión del mensaje. |

---

## 7. CLASES DE SERVICIO Y SOPORTE OPERATIVO (UTILIDADES)

### 7.1 Clase: `Cotizador` (Clase de Servicio)
- **Descripción:** Componente de lógica de negocio que encapsula las fórmulas matemáticas y comerciales de tarifación de encomiendas.
- **Paquete / Módulo:** `app.controllers.cotizador_controller`

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `calcularTarifa(envio: Envio, localidad: Localidad)` | `float` | Computa la tarifa base por distancia kilométrica, aplicando adicionales por seguros y fragilidad. |
| `+` | `aplicarDescuentoMultibulto(bultos: list)` | `float` | Aplica la regla comercial de descuento: 100% de cobro al primer bulto y 50% de bonificación a los siguientes. |

---

### 7.2 Clase: `GeneradorDocumentos` (Clase de Servicio)
- **Descripción:** Servicio utilitario encargado de componer, maquetar y renderizar los archivos imprimibles oficiales en formato PDF y etiquetas de códigos de barras.
- **Paquete / Módulo:** `app.services.generador_remito`

#### Métodos / Operaciones
| Visibilidad | Firma del Método | Retorno | Descripción Funcional |
|:---:|---|:---:|---|
| `+` | `generarComprobanteServicio(envio: Envio)` | `ArchivoPDF` | Emite el comprobante de recepción para entrega en ventanilla con el detalle económico. |
| `+` | `generarEtiquetaCode128(envio: Envio)` | `ArchivoPDF` | Produce la etiqueta térmica de 100x150 mm con código de barras Code128 para estiba. |
| `+` | `generarRemitoEntrega(envio: Envio, intento: IntentoEntrega)` | `ArchivoPDF` | Genera el remito legal triplicado oficial para el chofer y cliente receptor. |
| `+` | `generarCredencialRetiro(envio: Envio)` | `ArchivoPDF` | Emite la credencial oficial de retiro en depósito central para encomiendas en custodia tras 3 visitas fallidas. |

---

*Fin del Diccionario de Datos — Diagrama de Clases UML FormoPack Express*  
*Documento normalizado según estándares de Ingeniería de Software para copiado directo a Word/PDF.*
