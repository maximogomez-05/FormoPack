# 📋 Informe de Implementación — Requisitos RF 3.0 a RF 3.3

**Fecha**: 2026-08-31  
**Sprint**: Logística y Despacho  
**Estado**: ✅ Completado  

---

## 🎯 Resumen Ejecutivo

Se implementó un sistema completo de **logística y despacho** que integra:
- **RF 3.1**: Gestión de flota (vehículos, capacidades, estados)
- **RF 3.2**: Armado de despachos (hojas de ruta, asignación chofer/vehículo)
- **RF 3.3**: Ruteo por kilometraje (ordenamiento automático de entregas)

La solución es **100% operativa** con persistencia en base de datos MySQL, sin dependencias de datos mockeados.

---

## 📂 ARCHIVOS CREADOS

### 1. `app/models/vehiculo.py` (NUEVO)
**Propósito**: Modelo de dominio para vehículos de la flota

**Funcionalidad**:
```python
class Vehiculo:
    - validar_datos(patente, capacidad_kg)  # Validación de entrada
    - esta_disponible()  # Estado del vehículo
    - asignar_ruta()  # Cambiar estado a "en_ruta"
    - liberar()  # Marcar como disponible
    - to_dict()  # Serializar a JSON
    - from_db_row()  # Factory desde BD
```

**Atributos**:
- `id_vehiculo`: ID único
- `patente`: Placa del vehículo (ej: ABC123)
- `capacidad_kg`: Peso máximo transportable
- `estado`: disponible | en_ruta | mantenimiento | fuera_de_servicio

**Excepciones**: `ValidationError` para patente vacía o capacidad ≤ 0

---

### 2. `app/models/hoja_ruta.py` (NUEVO)
**Propósito**: Modelo de despacho que agrupa envíos

**Funcionalidad**:
```python
class HojaRuta:
    - agregar_envio(envio)  # Añade envío a la ruta
    - ordenar_envios_por_distancia()  # Ruteo óptimo
    - total_km()  # Distancia total del recorrido
    - to_dict()  # Serializa con envíos ordenados
    - from_db_row()  # Factory desde BD
```

**Atributos**:
- `id_hoja_ruta`: ID único
- `nro_despacho`: Código único (ej: DES-2025-001)
- `id_chofer`: Usuario tipo chofer asignado
- `id_vehiculo`: Vehículo asignado
- `fecha_emision`: Timestamp de creación
- `_envios`: Lista de envíos (relación 1:N)

**Relaciones**:
- FK `id_chofer` → `usuarios.id_usuario` (donde tipo_usuario='chofer')
- FK `id_vehiculo` → `vehiculos.id_vehiculo`
- 1:N con `envios` (a través de `envios.id_hoja_ruta`)

---

### 3. `app/services/ruteo.py` (NUEVO)
**Propósito**: Servicio de optimización de rutas por distancia

**Funcionalidad**:
```python
class ServicioRuteo:
    + ordenar_envios_por_distancia(envios)  # Ordena por KM (ASC)
    + calcular_recorrido_total(envios)  # Suma distancias
    - _obtener_distancia(envio)  # Helper flexible (dict/obj)
```

**Comportamiento**:
- Entrada: Lista de envíos (dict o modelos)
- Salida: Misma lista ordenada por distancia
- Tiebreaker: Número de guía (alfabético)

**Ejemplo**:
```
Entrada:  [FPA-003(180km), FPA-001(40km), FPA-002(120km)]
Salida:   [FPA-001(40km), FPA-002(120km), FPA-003(180km)]
```

---

### 4. `app/controllers/logistica_controller.py` (NUEVO)
**Propósito**: Controlador que orquesta flota, despachos y ruteo con BD

**Métodos RF 3.1 - Gestión de Flota**:
```python
def listar_vehiculos() → List[dict]
    # SELECT * FROM vehiculos
    # Retorna: [{'id':1, 'patente':'ABC123', 'capacidad_kg':1200, 'estado':'disponible', ...}]

def obtener_vehiculo(id_vehiculo) → Vehiculo | None
    # SELECT * FROM vehiculos WHERE id_vehiculo = ?

def registrar_vehiculo(patente: str, capacidad_kg: float) → Vehiculo
    # INSERT INTO vehiculos (patente, capacidad_kg, estado='disponible')
    # Valida: patente no vacía, capacidad > 0
    # Retorna: Instancia Vehiculo creada
```

**Métodos RF 3.2 - Armado de Despachos**:
```python
def crear_hoja_ruta(nro_despacho, id_chofer, id_vehiculo, envios_ids) → HojaRuta
    # INSERT INTO hojas_de_ruta (nro_despacho, id_chofer, id_vehiculo)
    # UPDATE envios SET id_hoja_ruta = ?, estado_actual = 'en_planta'
    # Retorna: Hoja completa con envíos

def obtener_hoja_ruta(id_hoja_ruta) → HojaRuta | None
    # SELECT FROM hojas_de_ruta + JOIN envios + JOIN localidades
    # Retorna: HojaRuta con envíos ya ordenados por distancia

def listar_hojas_ruta() → List[dict]
    # SELECT hojas_de_ruta.*, chofer.nombre, vehiculo.patente, COUNT(envios)
    # Retorna: Últimas 50 hojas con resumen
```

**Métodos RF 3.3 - Ruteo por Kilometraje**:
```python
def obtener_entregas_pendientes(estado='recibido') → List[dict]
    # SELECT envios.* FROM envios 
    # WHERE estado_actual = 'recibido' AND id_hoja_ruta IS NULL
    # JOIN localidades para traer distancia_km
    # Retorna: Entregas listas para despachar

def sugerir_ruta_optima(entregas) → List[dict]
    # Wrapper de ServicioRuteo.ordenar_envios_por_distancia()
    # Ordena de más cercana a más lejana

def calcular_carga_total(envios_ids: List[int]) → float
    # SELECT SUM(bultos.peso_real) FROM bultos WHERE id_envio IN (...)
    # Retorna: Peso total en KG
```

**Excepciones Manejadas**:
- `DatabaseConnectionError`: Sin acceso a BD
- `DatabaseQueryError`: Error en SQL
- `ValidationError`: Datos inválidos

---

### 5. `web/templates/admin/logistica.html` (NUEVO)
**Propósito**: Interfaz visual de logística

**Secciones**:
1. **Resumen de Logística** (4 métricas)
   - Recorrido total estimado (KM)
   - Entregas pendientes (cantidad)
   - Vehículos totales (cantidad)
   - Despachos activos (cantidad)

2. **Entregas ordenadas por distancia** (Tabla con RF 3.3)
   - Orden (1, 2, 3...)
   - Nº Guía
   - Localidad Destino
   - Distancia desde centro (KM)
   - Peso Total (KG)
   - Estado (recibido)

3. **Flota disponible** (Tabla con RF 3.1)
   - Patente
   - Capacidad (KG)
   - Estado (disponible/en_ruta/mantenimiento)
   - Indicador de disponibilidad (✓ Disponible / ⏱ Ocupado)

4. **Hojas de ruta activas** (Tabla con RF 3.2)
   - Nº Despacho
   - Chofer (nombre)
   - Vehículo (patente)
   - Entregas (cantidad)
   - Distancia Máxima (KM)
   - Fecha de emisión

**Mensajes Condicionales**:
- Si error BD: "No se puede conectar a la base de datos"
- Si sin entregas: "No hay entregas pendientes para despachar"
- Si sin vehículos: "No hay vehículos registrados en la flota"
- Si sin hojas: "No hay hojas de ruta activas. Crea una nueva..."

---

### 6. `scripts/run_tests.bat` (NUEVO)
**Propósito**: Script para ejecutar pruebas desde Windows

```batch
cd "C:\Users\maxim\OneDrive\Escritorio\Paqueteria\FormoPack"
python tests/test_modelos.py
```

---

## 🔧 ARCHIVOS MODIFICADOS

### 1. `web/app.py`
**Cambio**: Importar `request` para fix de seguridad

```python
# ANTES:
from flask import Flask, redirect, url_for

# DESPUÉS:
from flask import Flask, redirect, url_for, request
```

**Motivo**: La función `add_security_headers()` usa `request.endpoint` sin importarlo.

---

### 2. `web/routes/admin.py`
**Cambios**: 

**a) Imports nuevos**:
```python
# Agregar:
from app.controllers.logistica_controller import LogisticaController
from app.models.vehiculo import Vehiculo  # Para type hints
from app.models.hoja_ruta import HojaRuta  # Para type hints
```

**b) Nueva ruta `/admin/logistica`**:
```python
@admin_bp.route("/logistica", methods=["GET"])
@login_required
@rol_requerido("administrador", "recepcionista")
def logistica():
    """Pantalla de logística con flota, despacho y ruteo (RF 3.0 a RF 3.3)."""
    logistica_ctrl = LogisticaController()
    entregas_pendientes = []
    vehiculos = []
    hojas_activas = []
    total_km = 0.0
    error = None

    try:
        vehiculos = logistica_ctrl.listar_vehiculos()
        entregas_pendientes = logistica_ctrl.obtener_entregas_pendientes(estado="recibido")
        entregas_ordenadas = logistica_ctrl.sugerir_ruta_optima(entregas_pendientes)
        total_km = sum(float(e.get("distancia_km", 0.0)) for e in entregas_ordenadas)
        hojas_activas = logistica_ctrl.listar_hojas_ruta()
        entregas_pendientes = entregas_ordenadas

    except DatabaseConnectionError as e:
        error = "No se puede conectar a la base de datos"
        logger.error("Error de conexión en logística: %s", e)
    except Exception as e:
        error = str(e)
        logger.error("Error en logística: %s", e)

    return render_template(
        "admin/logistica.html",
        entregas=entregas_pendientes,
        vehiculos=vehiculos,
        hojas_activas=hojas_activas,
        total_km=total_km,
        error=error,
    )
```

**Funcionalidad**:
- Lee vehículos desde BD
- Lee entregas no asignadas (estado='recibido')
- Ordena automáticamente por distancia
- Suma KM totales
- Obtiene despachos activos
- Renderiza con datos reales

---

### 3. `web/templates/base.html`
**Cambio**: Agregar enlace en menú de navegación

```html
<!-- ANTES: -->
{% if session.rol == 'administrador' %}
<div class="nav-section" style="margin-top:12px;">Administración</div>
<a href="{{ url_for('admin.dashboard') }}" class="nav-link ...">
  <i class="fa-solid fa-chart-line nav-icon"></i> Panel de Control
</a>
{% endif %}

<!-- DESPUÉS: Agregar esta línea -->
<a href="{{ url_for('admin.logistica') }}" class="nav-link {% if request.endpoint == 'admin.logistica' %}active{% endif %}">
  <i class="fa-solid fa-truck-fast nav-icon"></i> Logística
</a>
```

**Impacto**: Menú ahora tiene acceso a `/admin/logistica` para administradores y recepcionistas.

---

### 4. `tests/test_modelos.py`
**Cambios**: Agregar pruebas para RF 3.0-3.3

**a) Imports nuevos**:
```python
from app.models.vehiculo import Vehiculo
from app.models.hoja_ruta import HojaRuta
from app.services.ruteo import ServicioRuteo
```

**b) Nuevas pruebas unitarias**:

```python
def test_vehiculo_validacion():
    """Prueba validación de patente y capacidad vehicular."""
    # Datos válidos
    Vehiculo.validar_datos("ABC123", 1200.0)
    Vehiculo.validar_datos("AB-123-CD", 2000.0)
    
    # Debe fallar con patente vacía
    try:
        Vehiculo.validar_datos("", 1000.0)
        assert False
    except ValidationError:
        pass
    
    # Debe fallar con capacidad ≤ 0
    try:
        Vehiculo.validar_datos("ABC123", 0)
        assert False
    except ValidationError:
        pass
    
    print("  [OK] Vehiculo: Validación de patente y capacidad")


def test_ruteo_por_kilometraje():
    """Prueba ordenamiento de entregas por distancia."""
    entregas = [
        {"nro_guia": "FPA-003", "id_localidad_destino": 2, "distancia_km": 180.0},
        {"nro_guia": "FPA-001", "id_localidad_destino": 1, "distancia_km": 40.0},
        {"nro_guia": "FPA-002", "id_localidad_destino": 3, "distancia_km": 120.0},
    ]
    orden = ServicioRuteo.ordenar_envios_por_distancia(entregas)
    assert [e["nro_guia"] for e in orden] == ["FPA-001", "FPA-002", "FPA-003"]
    
    # Test con HojaRuta
    hoja = HojaRuta(id_hoja_ruta=1, nro_despacho="DES-001", 
                    id_chofer=8, id_vehiculo=4)
    for e in entregas:
        hoja.agregar_envio(e)
    
    assert len(hoja.envios) == 3
    assert [e["nro_guia"] for e in hoja.ordenar_envios_por_distancia()] == ["FPA-001", "FPA-002", "FPA-003"]
    print("  [OK] Ruteo: ordenamiento por kilometraje")


def test_logistica_flujo_completo():
    """Prueba el flujo completo de logística: vehículos → hojas → ruteo."""
    # RF 3.1: Crear vehículos
    v1 = Vehiculo(1, "FPX-001", 1200.0, "disponible")
    v2 = Vehiculo(2, "FPX-002", 800.0, "disponible")
    assert v1.esta_disponible() is True
    assert v2.esta_disponible() is True
    print("  [OK] RF 3.1: Gestión de flota (vehículos registrados)")

    # RF 3.3: Ordenar entregas por distancia
    entregas = [
        {"id_envio": 1, "nro_guia": "FPX-001", "localidad_destino": "Clorinda", 
         "distancia_km": 120.0, "peso_total_kg": 45.0},
        {"id_envio": 2, "nro_guia": "FPX-002", "localidad_destino": "Herradura", 
         "distancia_km": 40.0, "peso_total_kg": 12.0},
        {"id_envio": 3, "nro_guia": "FPX-003", "localidad_destino": "Pirané", 
         "distancia_km": 180.0, "peso_total_kg": 88.0},
    ]
    ruta_optima = ServicioRuteo.ordenar_envios_por_distancia(entregas)
    assert [e["nro_guia"] for e in ruta_optima] == ["FPX-002", "FPX-001", "FPX-003"]
    print("  [OK] RF 3.3: Ruteo por kilometraje (entregas ordenadas)")

    # RF 3.2: Crear hoja de ruta
    hoja = HojaRuta(
        id_hoja_ruta=1,
        nro_despacho="DES-2025-001",
        id_chofer=8,
        id_vehiculo=1,
        envios=entregas,
    )
    assert len(hoja.envios) == 3
    assert hoja.total_km() == 340.0
    print("  [OK] RF 3.2: Armado de despachos (hoja de ruta creada con envíos)")
```

**b) Actualizar `main()`**:
```python
def main():
    print("\n--- Pruebas Sprint 2 (Modelos de Dominio) ---")
    # ... pruebas anteriores ...
    test_vehiculo_validacion()
    test_ruteo_por_kilometraje()
    test_logistica_flujo_completo()
    test_serialization()
    print("--- Todas las pruebas de modelos pasaron ---\n")
```

---

## 🗄️ CAMBIOS EN BASE DE DATOS

**Archivo**: `scripts/init_database.sql` (sin cambios, ya tenía las tablas)

**Tablas utilizadas**:

### `vehiculos`
```sql
CREATE TABLE vehiculos (
    id_vehiculo INT PRIMARY KEY AUTO_INCREMENT,
    patente VARCHAR(10) UNIQUE NOT NULL,
    capacidad_kg DECIMAL(10,2) NOT NULL,
    estado VARCHAR(30) DEFAULT 'disponible'
);
```

**Estados válidos**: disponible, en_ruta, mantenimiento, fuera_de_servicio

### `hojas_de_ruta`
```sql
CREATE TABLE hojas_de_ruta (
    id_hoja_ruta INT PRIMARY KEY AUTO_INCREMENT,
    nro_despacho VARCHAR(20) UNIQUE NOT NULL,
    fecha_emision DATETIME DEFAULT CURRENT_TIMESTAMP,
    id_chofer INT NOT NULL,
    id_vehiculo INT NOT NULL,
    FOREIGN KEY (id_chofer) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
);
```

### `envios` (ya existía, se usa campo `id_hoja_ruta`)
```sql
ALTER TABLE envios ADD COLUMN id_hoja_ruta INT DEFAULT NULL;
ALTER TABLE envios ADD FOREIGN KEY (id_hoja_ruta) REFERENCES hojas_de_ruta(id_hoja_ruta);
```

**Relación**: `envios.id_hoja_ruta` → `hojas_de_ruta.id_hoja_ruta`

### Queries SQL implementadas

**Listar vehículos**:
```sql
SELECT id_vehiculo, patente, capacidad_kg, estado FROM vehiculos ORDER BY patente
```

**Obtener entregas pendientes**:
```sql
SELECT e.id_envio, e.nro_guia, e.estado_actual, l.id_localidad, l.nombre, l.distancia_km,
       SUM(b.peso_real) as peso_total_kg
FROM envios e
JOIN localidades l ON e.id_localidad_destino = l.id_localidad
LEFT JOIN bultos b ON e.id_envio = b.id_envio
WHERE e.estado_actual = 'recibido' AND e.id_hoja_ruta IS NULL
GROUP BY e.id_envio
ORDER BY l.distancia_km ASC
```

**Listar hojas de ruta activas**:
```sql
SELECT hr.id_hoja_ruta, hr.nro_despacho, hr.fecha_emision, u.nombre as chofer_nombre,
       v.patente, COUNT(e.id_envio) as cantidad_envios, MAX(l.distancia_km) as max_distancia
FROM hojas_de_ruta hr
JOIN usuarios u ON hr.id_chofer = u.id_usuario
JOIN vehiculos v ON hr.id_vehiculo = v.id_vehiculo
LEFT JOIN envios e ON hr.id_hoja_ruta = e.id_hoja_ruta
LEFT JOIN localidades l ON e.id_localidad_destino = l.id_localidad
GROUP BY hr.id_hoja_ruta
ORDER BY hr.fecha_emision DESC
LIMIT 50
```

---

## 🧪 PRUEBAS INCLUIDAS

**Archivo**: `tests/test_modelos.py`

**Pruebas nuevas**:
1. ✅ `test_vehiculo_validacion()` — Valida patente y capacidad
2. ✅ `test_ruteo_por_kilometraje()` — Ordena entregas por distancia
3. ✅ `test_logistica_flujo_completo()` — E2E RF 3.1, 3.2, 3.3

**Cómo ejecutar**:
```bash
cd FormoPack
python tests/test_modelos.py
```

**Salida esperada**:
```
--- Pruebas Sprint 2 (Modelos de Dominio) ---
  [OK] Cliente: Validación de datos correctos
  [OK] Cliente: Validación de datos inválidos
  ...
  [OK] RF 3.1: Gestión de flota (vehículos registrados)
  [OK] RF 3.3: Ruteo por kilometraje (entregas ordenadas)
  [OK] RF 3.2: Armado de despachos (hoja de ruta creada con envíos)
  [OK] Serialización to_dict() de todos los modelos
--- Todas las pruebas de modelos pasaron ---
```

---

## 🎮 CÓMO PROBAR EN LA WEB

### 1. Preparar ambiente
```bash
# Instalar dependencias (si no las tenés)
pip install -r requirements.txt

# Configurar BD en .env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=formopack_db
DB_USER=root
DB_PASSWORD=tu_password
```

### 2. Inicializar BD
```bash
mysql -u root -p < scripts/init_database.sql
```

### 3. Insertar datos de prueba (opcional)
```bash
# Vehículos
INSERT INTO vehiculos (patente, capacidad_kg, estado) VALUES 
  ('ABC-123', 1200, 'disponible'),
  ('DEF-456', 800, 'disponible'),
  ('GHI-789', 1500, 'en_ruta');

# Usuarios chofer (para hojas de ruta)
INSERT INTO usuarios (nombre, email, credenciales_hash, tipo_usuario) VALUES
  ('Juan Pérez', 'juan@formopack.com', '$2b$12$...', 'chofer'),
  ('María López', 'maria@formopack.com', '$2b$12$...', 'chofer');
```

### 4. Iniciar la app
```bash
python web/app.py
```

### 5. Acceder a la interfaz
- URL: `http://localhost:5000/login`
- Rol: Administrador o Recepcionista
- Menú: **Logística**
- Pantalla: Mostrará vehículos, entregas ordenadas y hojas de ruta activas desde BD

---

## 📊 RESUMEN DE CAMBIOS

| Tipo | Cantidad | Descripción |
|------|----------|-------------|
| **Archivos Creados** | 6 | Modelos, servicios, controlador, template, script |
| **Archivos Modificados** | 4 | app.py, admin.py, base.html, test_modelos.py |
| **Líneas de Código Nuevas** | ~800 | Controlador, modelos, template, tests |
| **Clases Nuevas** | 3 | Vehiculo, HojaRuta, ServicioRuteo |
| **Métodos Nuevos** | 12+ | En LogisticaController y modelos |
| **Queries SQL** | 4 | Listar vehículos, entregas, hojas, etc. |
| **Pruebas Nuevas** | 3 | RF 3.1, 3.3, flujo E2E |
| **Requisitos Cubiertos** | 100% | RF 3.0, 3.1, 3.2, 3.3 |

---

## 🔐 PERMISOS Y ROLES

**Acceso a Logística**: Solo administrador y recepcionista

```python
@rol_requerido("administrador", "recepcionista")
def logistica():
    ...
```

**Datos visibles**:
- ✅ Vehículos: todos
- ✅ Entregas pendientes: solo no asignadas
- ✅ Hojas de ruta: últimas 50 (ORDER BY fecha DESC)

---

## 🚀 PRÓXIMOS PASOS (Opcionales)

1. **Crear endpoints AJAX** para crear hoja de ruta desde UI
2. **Dashboard de chofer** para ver su despacho asignado
3. **Historial de cambios** de estado (en_planta → en_ruta → entregado)
4. **Reportes de flota** (utilización, KM/mes, etc.)
5. **Notificaciones** al chofer cuando se asigna hoja de ruta
6. **Integración GPS** para tracking en vivo

---

## ✅ CHECKLIST DE VALIDACIÓN

- ✅ Modelos de dominio implementados (Vehiculo, HojaRuta)
- ✅ Servicio de ruteo funcional (ServicioRuteo)
- ✅ Controlador con lógica de negocio (LogisticaController)
- ✅ Integración con BD (queries SQL)
- ✅ Ruta Flask funcional (/admin/logistica)
- ✅ Template HTML con 4 secciones
- ✅ Pruebas unitarias de RF 3.0-3.3
- ✅ Validación de datos de entrada
- ✅ Manejo de errores (BD, validación)
- ✅ Permisos y roles correctos
- ✅ Documentación de cambios (este informe)

---

## 📝 Notas Técnicas

- **Patrón**: MVC (Modelos + Controlador + Vistas)
- **Base de datos**: MySQL 8.0+, InnoDB, charset utf8mb4
- **Lenguaje**: Python 3.10+, Flask 2.0+
- **Persistencia**: 100% en BD, sin datos mockeados
- **Validación**: A nivel de modelo y base de datos
- **Transacciones**: Usa connection.commit() para integridad
- **Seguridad**: Solo acceso con permisos verificados

---

**Generado**: 2026-08-31  
**Versión del Sistema**: FormoPack Express v1.0  
**Sprint**: Sprint 2 (Logística y Despacho)
