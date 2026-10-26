# FormoPack Express 📦🚚

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-black)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)
![Estado](https://img.shields.io/badge/Estado-En_validación-yellow.svg)

El proyecto está en una etapa de validación y ajustes previos al despliegue.
El [plan de implementación](docs/PLAN_IMPLEMENTACION.md) registra requisitos,
criterios de aceptación, incrementos terminados y cambios para los diagramas.

**Instalaciones existentes:** antes de usar esta versión, aplicar la migración
de [seguridad de acceso](docs/SEGURIDAD_ACCESO.md). Con la aplicación detenida y
un respaldo de la base, ejecutar `py -m app.core.migrations --desde 005` desde
la raíz del proyecto. No volver a inicializar una base de trabajo como mecanismo
de actualización.

La actualización también incluye [soporte exclusivo y cierre de chats](docs/SOPORTE.md).
Si la migración 005 ya estaba aplicada, ejecutar `py -m app.core.migrations --desde 006`
con respaldo previo y la aplicación detenida. Las migraciones se ejecutan fuera
del arranque web.

Para una instalación con 005 y 006 aplicadas, el incremento de
[pagos verificados y acabado visual](docs/PAGOS_MERCADOPAGO.md) requiere
`py -m app.core.migrations --desde 007`, con aplicación detenida y respaldo
comprobado. Configurar `MP_COLLECTOR_ID`, `MP_WEBHOOK_SECRET` y `MP_TEST_MODE`
además del token; una referencia QR manual ya no acredita un pago de Mercado Pago.

El incremento de [primer acceso y navegación](docs/PRIMER_ACCESO_Y_NAVEGACION.md)
requiere `py -m app.core.migrations --desde 008`. Las cuentas nuevas deben
reemplazar su contraseña provisoria antes de operar; las existentes se conservan.

**FormoPack Express** es un Sistema de Gestión Logística integral diseñado para automatizar el registro, cotización, seguimiento y entrega de encomiendas. El objetivo principal es erradicar el uso de papel y planillas manuales, unificando la administración en mostrador, la logística (armado de hojas de ruta) y la operación en calle mediante una aplicación web *Mobile-First* para los choferes.

## 🏗️ Arquitectura y Tecnologías

El proyecto está construido bajo una arquitectura modular y Programación Orientada a Objetos (POO) estricta, priorizando la escalabilidad y el rendimiento.

- **Backend:** Python + Flask
- **Base de Datos:** MySQL (Modelo Relacional normalizado en 3FN)
- **Seguridad:** Cifrado de credenciales con Bcrypt (Contraseñas seguras), protección PRG contra reenvíos y headers Anti-Caché.
- **Integraciones:** Mercado Pago (Checkout Pro), Servicio SMTP Email (HTML Remitos), Mapas Interactivos (Leaflet.js).
- **Frontend Móvil:** Panel *Mobile-First* (PWA) con capacidades Offline (Service Workers).

## 📊 Módulos del Sistema

Los siguientes módulos tienen implementación. Su validación integral y los
pendientes se detallan en el plan; esta lista no certifica cumplimiento total:

- [x] **RF 1: Gestión de Usuarios:** Autenticación y control de accesos por roles (Administrador, Recepcionista, Chofer).
- [x] **RF 2: Recepción y Facturación:** Cotizador automático, gestión de clientes, cobro en efectivo y cobro dinámico con código QR vía **Mercado Pago**.
- [x] **RF 3: Logística y Despacho:** Gestión de flota y vehículos, ruteo automático por geolocalización, generación de despachos y asignación de Hojas de Ruta.
- [x] **RF 4: App Móvil para Choferes (PWA):** Interfaz para celular. Prueba de Entrega (POD) con captura de firma digital en pantalla y sincronización offline en zonas sin cobertura.
- [x] **RF 5: Tracking y Dashboards:** Panel gerencial con estadísticas financieras, portal público de seguimiento de envíos interactivo, y motor de **Notificaciones por Email Automáticas** ante cambios de estado.

## 🚀 Instalación para ejecutar en OTRA PC

Si querés levantar este proyecto en una computadora nueva o pasárselo a un profesor, asegurate de seguir estos pasos EXACTAMENTE en orden:

### Prerrequisitos
- Python 3.10 o superior
- Servidor MySQL 8.0+ (Por ejemplo: XAMPP)

### Pasos
1. **Crear la Base de Datos:**
   - Abrí phpMyAdmin (o tu gestor de MySQL).
   - Ejecutá el archivo completo que está en `scripts/init_database.sql`. Esto va a crear la base de datos `formopack_db`, construir todas las tablas y cargar datos semilla (localidades, etc).
   - Si la base ya existía antes del seguimiento GPS, ejecutá una vez `scripts/migracion_ubicaciones_gps.sql` sobre `formopack_db` para crear la tabla de última ubicación de ruta.

2. **Configurar las Variables de Entorno (.env):**
   - En la carpeta raíz del proyecto, hacé una copia del archivo `.env.example` y nombralo `.env`.
   - Abrí el `.env` y asegurate de que los datos de tu Base de Datos coincidan (usuario `root`, sin contraseña, puerto `3306`).
   - Para enviar alertas por Gmail, completá `GMAIL_USER`, `GMAIL_APP_PASSWORD` y `ALERTAS_EMAIL` usando los nombres de `.env.example`. La contraseña debe ser una contraseña de aplicación de Google; requiere tener habilitada la verificación en dos pasos. No uses ni compartas tu contraseña habitual.
   - Mercado Pago es opcional; completá sus credenciales solo si querés probar esa integración.

3. **Crear Entorno Virtual e Instalar Dependencias:**
   Abrí la terminal en la carpeta del proyecto y ejecutá:
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Linux/Mac:
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

4. **Ejecutar el Servidor:**
   ```bash
   python run.py
   ```
   *El sistema estará vivo y funcionando en: http://localhost:5050*

## 📁 Estructura del Proyecto

```text
FormoPack/
├── app/
│   ├── controllers/   # Lógica central del negocio (Controladores)
│   ├── core/          # Conexiones troncales (Ej: Database Manager Singleton)
│   ├── models/        # Entidades del negocio (POO: Envio, Cliente, Pago)
│   ├── services/      # Servicios de Terceros (Cotizador, MercadoPago, Emails)
│   └── utils/         # Excepciones personalizadas
├── web/
│   ├── routes/        # Enrutadores Flask (Views: admin, chofer, recepcion)
│   ├── static/        # Archivos estáticos (CSS SaaS, JS, PWA, Imágenes Locales)
│   └── templates/     # Interfaces de usuario en Jinja2 (HTML)
├── config/            # Configuraciones globales del entorno
├── scripts/           # init_database.sql (Toda la estructura SQL oficial)
├── run.py             # Punto de entrada de la aplicación web
└── requirements.txt   # Dependencias de Python
```

---
*Desarrollado para el Seminario de Integración.*
