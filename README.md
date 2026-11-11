# FormoPack Express — Sistema de Gestión Logística y Distribución

Sistema integral de gestión logística, trazabilidad y facturación desarrollado para el Seminario de Integración. La plataforma automatiza la recepción de encomiendas en Formosa Capital y su distribución hacia las distintas localidades del interior de la provincia (Clorinda, Pirané, El Colorado, Las Lomitas, entre otras), eliminando el uso de planillas físicas y unificando la administración en mostrador, el despacho de flota y la operación en calle de los choferes.

---

## Arquitectura y Tecnologías

El sistema está construido bajo principios de Programación Orientada a Objetos (POO), arquitectura modular por capas y separación estricta de responsabilidades:

- **Lenguaje y Framework:** Python 3.10+ con Flask (Blueprints modulares y plantillas Jinja2).
- **Base de Datos:** MySQL 8.0+ (modelo relacional normalizado en 3FN, conexión mediante DatabaseManager bajo patrón Singleton).
- **Seguridad:** Cifrado de credenciales con Bcrypt, control de acceso basado en roles (RBAC), protección contra ataques CSRF, validación estricta de estados y protección Post/Redirect/Get (PRG).
- **Frontend y Diseño:** HTML5 semántico, CSS3 corporativo refinado, tipografías Plus Jakarta Sans y JetBrains Mono, Vanilla JS sin dependencias pesadas.
- **Geolocalización y Mapas:** Leaflet.js con OpenStreetMap y capas de telemetría en vivo.
- **Generación de Documentos:** ReportLab para constancias internas y actas de recepción en formato PDF.

---

## Módulos del Sistema

### 1. Tablero Operativo (Dashboard Central)
- **Atención requerida para iniciar la jornada:** Muestra de forma prioritaria los envíos listos para despacho, las visitas que admiten reprogramación tras intentos fallidos, las encomiendas pendientes de ingreso a central y los paquetes en resguardo con plazo vencido.
- **Operación de reparto:** Distingue los envíos acumulados del día de la situación en tiempo real de la flota (en ruta, en preparación o en planta).
- **Caja del día:** Separa el dinero efectivamente recaudado (efectivo y digital) del valor bruto tarifado de las guías registradas.
- **Reloj operativo en vivo:** Indicador de hora y fecha oficial de despacho (Formosa, UTC-3) con segundero continuo.

### 2. Recepción, Cotización y Caja
- Cotizador automático por peso, dimensiones volumétricas y localidad de destino.
- Registro y gestión de clientes remitentes y destinatarios.
- Cobro en mostrador mediante efectivo y pagos digitales (Mercado Pago).
- Turnos de caja con control de apertura y cierre de turno.

### 3. Logística, Despacho y Flota
- Registro de vehículos de transporte y capacidad de carga.
- Armado de hojas de ruta y asignación de encomiendas por cercanía geográfica.
- Mapa de operaciones con visualización de rutas provinciales (RN 11, RP 81) y estado de unidades en tránsito.

### 4. Custodia y Devoluciones en Central
- Control de encomiendas que retornan a Formosa Capital tras intentos fallidos o cancelaciones.
- Gestión del plazo reglamentario de 15 días corridos de resguardo en depósito central.
- Acta de entrega presencial al remitente con acreditación de identidad (DNI) y captura de firma digital en pantalla.
- Descarga de constancia firmada en formato PDF.

### 5. Portal de Seguimiento Público (Tracking)
- Búsqueda de guías con historial completo de eventos y marcas de tiempo.
- Geolocalización de la unidad en tránsito sobre mapa interactivo.
- Botones de acceso directo con guías de prueba para demostraciones.
- Canal integrado de atención y soporte al cliente en línea.

### 6. Aplicación de Reparto para Choferes (Mobile-First)
- Interfaz adaptada a dispositivos móviles para choferes en ruta.
- Registro de entregas efectivas con captura de firma digital del receptor.
- Registro de intentos fallidos y causas de no entrega para reprogramación operativa.

### 7. Gestión de Personal y Usuarios
- Directorio administrativo de cuentas con filtro por rol y buscador en tiempo real.
- Roles operativos diferenciados: Administrador, Recepcionista y Chofer.
- Suspensión y reactivación de accesos con confirmación de seguridad y protección contra auto-desactivación.

---

## Instalación y Configuración Local

### Requisitos Previos
- Python 3.10 o superior instalado.
- Servidor MySQL 8.0+ en ejecución (puerto estándar 3306).
- Git.

### Pasos de Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/maximogomez-05/formopack.git
   cd formopack
   ```

2. **Crear y activar el entorno virtual:**
   ```bash
   # En Windows:
   py -m venv venv
   venv\Scripts\activate

   # En Linux / macOS:
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar la base de datos:**
   - Crear una base de datos llamada `formopack_db` en el servidor MySQL.
   - Ejecutar el script de inicialización de estructura:
     ```bash
     mysql -u root -p formopack_db < scripts/init_database.sql
     ```
   - Si la base de datos ya existía, aplicar las migraciones pendientes con:
     ```bash
     py -m app.core.migrations
     ```
    - La optimización de flota usa OR-Tools y los nuevos campos de coordenadas, prioridad y ventana horaria. Instalar la dependencia y aplicar la migración correspondiente:
       ```bash
       py -m pip install -r requirements.txt
       py -m app.core.migrations
       ```
    - En Logística, seleccioná pedidos y elegí **Optimizar selección con toda la flota**. Los pedidos requieren pin manual para entrar al plan. Sin `FORMOPACK_OSRM_URL` configurada, las distancias son aproximaciones geográficas, no recorridos viales.

5. **Configurar las variables de entorno:**
   - Crear un archivo `.env` en la raíz del proyecto tomando como base `.env.example`:
     ```env
     SECRET_KEY=clave_secreta_de_desarrollo
     DB_HOST=127.0.0.1
     DB_PORT=3306
     DB_USER=root
     DB_PASSWORD=
     DB_NAME=formopack_db
     PORT=5050
     DEBUG=True
     ```

6. **Poblar datos de demostración (Opcional):**
   Para cargar un escenario completo de prueba (encomiendas en ruta, entregas con firma, retornos en custodia y usuarios de prueba):
   ```bash
   py scripts/seed_demo.py
   ```

7. **Iniciar la aplicación:**
   ```bash
   py run.py
   ```
   La aplicación quedará accesible en el navegador en: `http://localhost:5050`

---

## Cuentas de Acceso para Pruebas

Para evaluar los distintos roles del sistema, se encuentran disponibles las siguientes cuentas predeterminadas:

| Rol | Correo Electrónico | Contraseña | Alcance de Operación |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin@formopack.com` | `admin123` | Control total del sistema, comprobantes, logística, usuarios y liquidaciones. |
| **Recepcionista** | `recepcion@formopack.com` | `recep456` | Cotizador de envíos, nuevo remito, clientes, arqueo de caja y devoluciones en central. |
| **Chofer** | `chofer@formopack.com` | `chofer789` | Panel de entregas asignadas, telemetría GPS y captura de firma en destino. |

---

## Pruebas Automatizadas

El proyecto incluye un conjunto de pruebas unitarias y de integración desarrolladas con `pytest`:

```bash
# Ejecutar todas las pruebas del proyecto
py -m pytest

# Ejecutar pruebas del tablero operativo y comprobantes
py -m pytest tests/test_dashboard_pedidos.py tests/test_admin_comprobantes.py
```

---

## Estructura del Repositorio

```text
FormoPack/
├── app/
│   ├── controllers/      # Controladores de la lógica de negocio
│   ├── core/             # Conexión a base de datos y migraciones
│   ├── models/           # Entidades del modelo de dominio (POO)
│   ├── services/         # Servicios de cotización, pagos y logística
│   └── utils/            # Excepciones y utilidades de validación
├── config/               # Configuración del entorno y roles
├── docs/                 # Documentación técnica, estados y plan
├── scripts/              # Scripts de inicialización SQL y semillas de demo
├── tests/                # Suite de pruebas automatizadas (pytest)
├── web/
│   ├── routes/           # Enrutadores Flask por perfil de usuario
│   ├── security/         # Manejo de sesiones y autenticación
│   ├── static/           # Archivos estáticos (CSS, JS, iconos, imágenes)
│   └── templates/        # Plantillas HTML con motor Jinja2
├── .env.example          # Plantilla de variables de entorno
├── requirements.txt      # Lista de dependencias de Python
└── run.py                # Punto de entrada de ejecución del servidor
```

---

*Proyecto desarrollado para el Seminario de Integración.*
