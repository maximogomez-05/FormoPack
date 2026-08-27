# FormoPack Express 📦🚚

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)
![Estado](https://img.shields.io/badge/Estado-En%20Desarrollo-yellow.svg)

**FormoPack Express** es un Sistema de Gestión Logística integral diseñado para automatizar el registro, cotización, seguimiento y entrega de encomiendas. El objetivo principal es erradicar el uso de papel y planillas manuales, unificando la administración en mostrador, la logística (armado de hojas de ruta) y la operación en calle mediante una aplicación móvil para los choferes.

## 🚀 Arquitectura y Tecnologías

El proyecto está construido bajo una arquitectura modular (MVC) y Programación Orientada a Objetos (POO) estricta, priorizando la escalabilidad y el rendimiento.

- **Lenguaje Principal:** Python
- **Base de Datos:** MySQL (Modelo Relacional normalizado en 3FN)
- **Seguridad:** Cifrado de credenciales con Bcrypt (Contraseñas seguras)
- **Paradigma:** Orientado a Objetos (POO)
- **Frontend Móvil (Planeado):** PWA (Progressive Web App) con capacidades Offline (LocalStorage).

## 🧩 Módulos del Sistema

El sistema se divide en 5 grandes módulos funcionales:

- [x] **RF 1: Gestión de Usuarios:** Control de accesos y roles (Administrador, Recepcionista, Chofer).
- [ ] **RF 2: Recepción y Facturación:** Cotizador por aforo, regla multibulto, integración de pagos (QR/MercadoPago) y cierres de caja.
- [ ] **RF 3: Logística y Despacho:** Gestión de flota, armado de hojas de ruta, ruteo por kilometraje y emisión de etiquetas/remitos.
- [ ] **RF 4: App Móvil para Choferes (PWA):** Prueba de Entrega (POD) con foto/firma, alertas por WhatsApp y sincronización offline en zonas sin cobertura.
- [ ] **RF 5: Tracking y Dashboards:** Portal público de seguimiento de envíos (Timeline) y métricas gerenciales.

## ⚙️ Instalación y Configuración Local

### Prerrequisitos
- Python 3.10 o superior
- Servidor MySQL 8.0+

### Pasos
1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-usuario/FormoPack.git
   cd FormoPack
   ```

2. **Crear y activar un entorno virtual:**
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Linux/Mac:
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuración de Entorno:**
   - Copiar el archivo `.env.example` a un nuevo archivo llamado `.env`
   - Configurar las credenciales de la base de datos MySQL en el `.env`.

5. **Ejecutar Pruebas Base (Verificación):**
   ```bash
   python main.py
   ```

## 📂 Estructura del Proyecto

```text
FormoPack/
├── app/
│   ├── controllers/   # Controladores (Lógica de negocio e intermediarios)
│   ├── core/          # Configuraciones base (Ej: Conexión a Base de Datos)
│   ├── models/        # Entidades del negocio (POO)
│   └── utils/         # Funciones auxiliares y manejo de excepciones
├── config/            # Configuraciones globales del sistema
├── scripts/           # Scripts de mantenimiento (migraciones, automatizaciones)
├── tests/             # Pruebas unitarias
├── .env.example       # Plantilla de variables de entorno
├── main.py            # Punto de entrada de la aplicación
└── requirements.txt   # Dependencias del proyecto
```

---
*Desarrollado para el Seminario de Integración.*
