"""
Script de Semillas para Demostración (Showcase Demo) — FormoPack Express.
Puebla la base de datos con un escenario operativo completo, realista y coherente
para la presentación académica del proyecto.

Ejecutar con:
    py scripts/seed_demo.py
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from config.settings import RoleConfig

# SVG simulado para firma digital de entrega (POD)
FIRMA_DEMO_SVG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMDAiIGhlaWdodD0iMTAwIj48cGF0aCBkPSJNMTAgODAgUTk1IDEwIDE4MCA4MCBUMjkwIDcwIiBzdHJva2U9IiMxNzZiODciIHN0cm9rZS13aWR0aD0iMyIgZmlsbD0ibm9uZSIvPjwvc3ZnPg=="

def limpiar_tablas(cur):
    """Limpia las tablas operativas preservando las tablas maestras."""
    tablas = [
        "revisiones_pago_mp",
        "mensajes_soporte",
        "chats_soporte",
        "operaciones_visita",
        "intentos_entrega",
        "retiros_central",
        "hojas_ruta_envios",
        "ubicaciones_hojas_ruta",
        "historial_estados",
        "bultos",
        "pagos",
        "ordenes_pago_mp",
        "comprobantes_internos",
        "envios",
        "hojas_de_ruta",
        "turnos_caja",
        "vehiculos",
        "clientes",
    ]
    cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
    for t in tablas:
        try:
            cur.execute(f"TRUNCATE TABLE {t};")
        except Exception as e:
            cur.execute(f"DELETE FROM {t};")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1;")
    print("  [OK] Tablas operativas limpiadas.")


def seed_usuarios(cur):
    """Garantiza la existencia y contraseñas de los usuarios de prueba."""
    usuarios = [
        ("Administrador Sistema", "admin@formopack.com", "admin123", RoleConfig.ADMINISTRADOR, None),
        ("Maria Recepcionista", "recepcion@formopack.com", "recep456", RoleConfig.RECEPCIONISTA, None),
        ("Carlos Chofer", "chofer@formopack.com", "chofer789", RoleConfig.CHOFER, "LI-123456"),
        ("Juan Repartidor", "chofer2@formopack.com", "chofer789", RoleConfig.CHOFER, "LI-987654"),
    ]
    sql = """
        INSERT INTO usuarios (nombre, email, credenciales_hash, tipo_usuario, nro_licencia, activo, debe_cambiar_password, version_sesion)
        VALUES (%s, %s, %s, %s, %s, 1, 0, 0)
        ON DUPLICATE KEY UPDATE
            credenciales_hash = VALUES(credenciales_hash),
            tipo_usuario = VALUES(tipo_usuario),
            activo = 1,
            debe_cambiar_password = 0;
    """
    for nom, email, pw, rol, lic in usuarios:
        h = Usuario.hashear_password(pw)
        cur.execute(sql, (nom, email, h, rol, lic))
    print("  [OK] Usuarios base garantizados.")


def seed_vehiculos(cur):
    """Carga la flota de vehículos."""
    vehiculos = [
        (1, "AF-123-CD", Decimal("800.00"), "en_ruta"),       # Renault Kangoo (en viaje a Clorinda)
        (2, "AE-982-ZZ", Decimal("1500.00"), "disponible"),    # Mercedes Sprinter (disponible en base)
        (3, "AD-456-XY", Decimal("3500.00"), "disponible"),    # Iveco Daily (disponible en base)
        (4, "AC-789-JK", Decimal("1000.00"), "mantenimiento"), # Toyota Hilux (en taller)
    ]
    for vid, pat, cap, est in vehiculos:
        cur.execute(
            "INSERT INTO vehiculos (id_vehiculo, patente, capacidad_kg, estado) VALUES (%s, %s, %s, %s);",
            (vid, pat, cap, est)
        )
    print("  [OK] Flota de vehículos cargada (4 unidades).")


def seed_clientes(cur):
    """Carga clientes remitentes y destinatarios representativos."""
    clientes = [
        (1, "28111222", "Juan Carlos Pérez", "3704112233", "jperez@gmail.com"),
        (2, "32333444", "María Elena Gómez", "3718445566", "mgomez@hotmail.com"),
        (3, "20345678", "Distribuidora Norte SRL", "3704556677", "ventas@distribuidoranorte.com"),
        (4, "35789123", "Roberto Fernández", "3715889900", "rfernandez@yahoo.com"),
        (5, "27654321", "Farmacia San Martín", "3704223344", "contacto@farmaciasanmartin.com"),
        (6, "40123987", "Laura Benítez", "3716334455", "laura.benitez@gmail.com"),
    ]
    for cid, dni, nom, tel, mail in clientes:
        cur.execute(
            "INSERT INTO clientes (id_cliente, dni, nombre_completo, telefono, email) VALUES (%s, %s, %s, %s, %s);",
            (cid, dni, nom, tel, mail)
        )
    print("  [OK] Clientes cargados (6 remitentes/destinatarios).")


def seed_caja(cur):
    """Carga un turno cerrado de ayer y un turno ABIERTO para hoy."""
    ayer = datetime.now() - timedelta(days=1)
    hoy = datetime.now()

    # Turno 1: Ayer (Cerrado)
    cur.execute("""
        INSERT INTO turnos_caja (id_turno, id_recepcionista, fecha_apertura, fecha_cierre, saldo_inicial, ingresos_efectivo, ingresos_digitales, estado_caja)
        VALUES (1, 2, %s, %s, 10000.00, 35000.00, 28500.00, 'cerrado');
    """, (ayer.replace(hour=8, minute=0, second=0), ayer.replace(hour=19, minute=30, second=0)))

    # Turno 2: Hoy (Abierto por María Recepcionista para operar en la demo)
    cur.execute("""
        INSERT INTO turnos_caja (id_turno, id_recepcionista, fecha_apertura, fecha_cierre, saldo_inicial, ingresos_efectivo, ingresos_digitales, estado_caja)
        VALUES (2, 2, %s, NULL, 15000.00, 18500.00, 14500.00, 'abierto');
    """, (hoy.replace(hour=8, minute=15, second=0),))
    print("  [OK] Turnos de caja inicializados (Ayer cerrado, Hoy ABIERTO).")


def seed_hojas_y_envios(cur):
    """Carga despachos, envíos con diversos estados, bultos y pagos."""
    ahora = datetime.now()
    hace_2_dias = ahora - timedelta(days=2)
    ayer = ahora - timedelta(days=1)

    # ─────────────────────────────────────────────────────────────
    # HOJA DE RUTA 1: Ayer (Cerrada) - Reparto completado a Pirané
    # ─────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO hojas_de_ruta (id_hoja_ruta, nro_despacho, fecha_emision, id_chofer, id_vehiculo, estado, fecha_cierre)
        VALUES (1, 'DESP-2026-098', %s, 3, 2, 'cerrada', %s);
    """, (ayer.replace(hour=9, minute=0), ayer.replace(hour=16, minute=45)))

    # ─────────────────────────────────────────────────────────────
    # HOJA DE RUTA 2: Hoy (Activa / En Ruta) - Reparto a Clorinda
    # ─────────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO hojas_de_ruta (id_hoja_ruta, nro_despacho, fecha_emision, id_chofer, id_vehiculo, estado, fecha_cierre)
        VALUES (2, 'DESP-2026-101', %s, 3, 1, 'abierta', NULL);
    """, (ahora.replace(hour=9, minute=30),))

    # Telemetría GPS en vivo de la unidad AF-123-CD sobre Ruta Nacional 11 hacia Clorinda
    cur.execute("""
        INSERT INTO ubicaciones_hojas_ruta (id_hoja_ruta, id_chofer, latitud, longitud, precision_m, fecha_actualizacion)
        VALUES (2, 3, -25.5500000, -57.9000000, 8.50, %s);
    """, (ahora - timedelta(minutes=5),))

    # ─────────────────────────────────────────────────────────────
    # ENVÍOS PRINCIPALES DE LA DEMO
    # ─────────────────────────────────────────────────────────────

    # 1. ENVÍO FP-84920181: ENTREGADO (Demostración de POD con Firma y GPS)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (1, 'FP-84920181', 3, 4, 3, 1, 1, 'Av. Alberdi 450, Pirané', 45000.00, 'efectivo', 8500.00, 'entregado', 0, %s);
    """, (ayer.replace(hour=8, minute=30),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (1, 1, 6.50, 4.20, 0);")
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, monto_entregado) VALUES (1, 1, 1, 8500.00, %s, 'efectivo', 10000.00);", (ayer.replace(hour=8, minute=35),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (1, 1, 'REC-2026-0001', 'recepcion', %s);", (ayer.replace(hour=8, minute=35),))
    
    # Historial de estados de FP-84920181
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (1, %s, 'recibido', 'Sede Central Formosa', 'Recepción y cobro en mostrador');", (ayer.replace(hour=8, minute=35),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (1, %s, 'en_planta', 'Depósito Central', 'Asignado a despacho DESP-2026-098');", (ayer.replace(hour=9, minute=0),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (1, %s, 'en_ruta', 'Ruta Provincial 3', 'Chofer Carlos inició recorrido');", (ayer.replace(hour=9, minute=45),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (1, %s, 'entregado', 'Pirané', 'Entregado conforme a Roberto Fernández');", (ayer.replace(hour=14, minute=20),))
    
    # Intento de entrega exitoso con firma POD
    cur.execute("""
        INSERT INTO intentos_entrega (id_intento, id_envio, id_hoja_ruta, fecha_hora, coordenadas_gps, tipo_intento, dni_receptor, firma_receptor, foto_remito, motivo_fallo)
        VALUES (1, 1, 1, %s, '-25.7330000,-59.1080000', 'entregado', '35789123', %s, 'uploads/remitos/demo_remito.jpg', NULL);
    """, (ayer.replace(hour=14, minute=20), FIRMA_DEMO_SVG))
    cur.execute("INSERT INTO hojas_ruta_envios (id_hoja_ruta, id_envio, resolucion, fecha_resolucion) VALUES (1, 1, 'entregado', %s);", (ayer.replace(hour=14, minute=20),))

    # 2. ENVÍO FP-84920182: EN RUTA (Muestra Mapa Leaflet en Vivo y PWA Móvil)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (2, 'FP-84920182', 1, 2, 2, 2, 2, 'Av. San Martín 780, Clorinda', 75000.00, 'digital', 11500.00, 'en_ruta', 0, %s);
    """, (ahora.replace(hour=8, minute=45),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (2, 2, 8.00, 9.50, 0);")
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, id_transaccion_ext, billetera_virtual) VALUES (2, 2, 2, 11500.00, %s, 'digital', 'MP-99482103', 'MercadoPago');", (ahora.replace(hour=8, minute=50),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (2, 2, 'REC-2026-0002', 'recepcion', %s);", (ahora.replace(hour=8, minute=50),))
    
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (2, %s, 'recibido', 'Sede Central Formosa', 'Cobrado mediante QR Mercado Pago');", (ahora.replace(hour=8, minute=50),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (2, %s, 'en_planta', 'Depósito Central', 'Estibado en unidad AF-123-CD');", (ahora.replace(hour=9, minute=30),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (2, %s, 'en_ruta', 'Ruta Nacional 11', 'En tránsito hacia Clorinda');", (ahora.replace(hour=10, minute=0),))
    cur.execute("INSERT INTO hojas_ruta_envios (id_hoja_ruta, id_envio, resolucion, fecha_resolucion) VALUES (2, 2, NULL, NULL);")

    # 3. ENVÍO FP-84920183: EN RUTA (Segunda parada del despacho actual)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (3, 'FP-84920183', 5, 6, 2, 1, 2, 'Calle España 1200, Clorinda', 30000.00, 'efectivo', 7000.00, 'en_ruta', 0, %s);
    """, (ahora.replace(hour=9, minute=10),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (3, 3, 3.20, 2.50, 0);")
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, monto_entregado) VALUES (3, 3, 2, 7000.00, %s, 'efectivo', 10000.00);", (ahora.replace(hour=9, minute=15),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (3, 3, 'REC-2026-0003', 'recepcion', %s);", (ahora.replace(hour=9, minute=15),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (3, %s, 'recibido', 'Sede Central', 'Cobrado en mostrador');", (ahora.replace(hour=9, minute=15),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (3, %s, 'en_planta', 'Depósito', 'Asignado a DESP-2026-101');", (ahora.replace(hour=9, minute=30),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (3, %s, 'en_ruta', 'Ruta Nacional 11', 'En viaje hacia destino');", (ahora.replace(hour=10, minute=0),))
    cur.execute("INSERT INTO hojas_ruta_envios (id_hoja_ruta, id_envio, resolucion, fecha_resolucion) VALUES (2, 3, NULL, NULL);")

    # 4. ENVÍO FP-84920184: CUSTODIA CENTRAL TRAS 3 FALLOS (Para mostrar la Credencial de Retiro)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (4, 'FP-84920184', 3, 1, 1, 1, NULL, 'B° San Miguel, Calle Moreno 1450, Formosa', 60000.00, 'efectivo', 5500.00, 'devolucion', 1, %s);
    """, (hace_2_dias.replace(hour=10, minute=0),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (4, 4, 4.00, 3.50, 0);")
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, monto_entregado) VALUES (4, 4, 1, 5500.00, %s, 'efectivo', 6000.00);", (hace_2_dias.replace(hour=10, minute=5),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (4, 4, 'REC-2026-0004', 'recepcion', %s);", (hace_2_dias.replace(hour=10, minute=5),))
    
    # 3 Intentos fallidos registrados en días consecutivos
    cur.execute("INSERT INTO intentos_entrega (id_intento, id_envio, id_hoja_ruta, fecha_hora, coordenadas_gps, tipo_intento, motivo_fallo) VALUES (2, 4, 1, %s, '-26.1850,-58.1750', 'fallido', 'destinatario_ausente');", (hace_2_dias.replace(hour=14, minute=0),))
    cur.execute("INSERT INTO intentos_entrega (id_intento, id_envio, id_hoja_ruta, fecha_hora, coordenadas_gps, tipo_intento, motivo_fallo) VALUES (3, 4, 1, %s, '-26.1852,-58.1755', 'fallido', 'domicilio_cerrado');", (ayer.replace(hour=11, minute=30),))
    cur.execute("INSERT INTO intentos_entrega (id_intento, id_envio, id_hoja_ruta, fecha_hora, coordenadas_gps, tipo_intento, motivo_fallo) VALUES (4, 4, 1, %s, '-26.1851,-58.1751', 'fallido', 'no_responde_llamados');", (ayer.replace(hour=17, minute=15),))
    
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (4, %s, 'recibido', 'Sede Central', 'Recepción');", (hace_2_dias.replace(hour=10, minute=5),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (4, %s, 'fallido', 'Formosa', 'Visita 1: Destinatario ausente');", (hace_2_dias.replace(hour=14, minute=0),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (4, %s, 'fallido', 'Formosa', 'Visita 2: Domicilio cerrado sin respuesta');", (ayer.replace(hour=11, minute=30),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (4, %s, 'fallido', 'Formosa', 'Visita 3: Sin respuesta. Se activa protocolo de custodia.');", (ayer.replace(hour=17, minute=15),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (4, %s, 'devolucion', 'Depósito Central', 'En custodia de Almacén Central. Disponible para retiro presencial.');", (ayer.replace(hour=18, minute=0),))
    
    # Registro en retiros_central listo para demo de devolución
    cur.execute("""
        INSERT INTO retiros_central (id_envio, ingreso, recibe, vence, retiro, entrega, dni, firma)
        VALUES (4, %s, 1, %s, NULL, NULL, NULL, NULL);
    """, (ayer.replace(hour=18, minute=0), (ayer + timedelta(days=15)).date()))

    # 5. ENVÍO FP-84920185: RECIBIDO (Para la demo en vivo: crear Hoja de Ruta en mostrador)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (5, 'FP-84920185', 1, 6, 7, 2, NULL, 'Av. San Martín 300, Las Lomitas', 120000.00, 'digital', 14500.00, 'recibido', 0, %s);
    """, (ahora.replace(hour=8, minute=30),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (5, 5, 12.00, 10.00, 0);")
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, id_transaccion_ext, billetera_virtual) VALUES (5, 5, 2, 14500.00, %s, 'digital', 'MP-88124901', 'MercadoPago');", (ahora.replace(hour=8, minute=32),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (5, 5, 'REC-2026-0005', 'recepcion', %s);", (ahora.replace(hour=8, minute=32),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (5, %s, 'recibido', 'Sede Central Formosa', 'Cobro digital confirmado. Pendiente de asignación a despacho.');", (ahora.replace(hour=8, minute=32),))

    # 6. ENVÍO FP-84920186: RECIBIDO MULTIBULTO Y FRÁGIL (Muestra regla 100%/50% y +10% frágil)
    cur.execute("""
        INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
        VALUES (6, 'FP-84920186', 5, 2, 4, 1, NULL, 'Belgrano 650, El Colorado', 50000.00, 'efectivo', 16200.00, 'recibido', 0, %s);
    """, (ahora.replace(hour=9, minute=0),))
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (6, 6, 5.00, 4.00, 1);") # Bulto 1: 100% + 10%
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (7, 6, 4.00, 3.50, 0);") # Bulto 2: 50% desc
    cur.execute("INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES (8, 6, 4.00, 3.00, 0);") # Bulto 3: 50% desc
    cur.execute("INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, monto_entregado) VALUES (6, 6, 2, 16200.00, %s, 'efectivo', 20000.00);", (ahora.replace(hour=9, minute=5),))
    cur.execute("INSERT INTO comprobantes_internos (id_comprobante, id_envio, nro_comprobante, tipo_comprobante, fecha_emision) VALUES (6, 6, 'REC-2026-0006', 'recepcion', %s);", (ahora.replace(hour=9, minute=5),))
    cur.execute("INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES (6, %s, 'recibido', 'Sede Central', 'Envío multibulto frágil cobrado con vuelto.');", (ahora.replace(hour=9, minute=5),))

    # ─────────────────────────────────────────────────────────────
    # ENVÍOS HISTÓRICOS ADICIONALES (Para dibujar la curva semanal del Dashboard)
    # ─────────────────────────────────────────────────────────────
    dias_atras = [6, 5, 4, 3, 2]
    costos = [18500.00, 24000.00, 31500.00, 22000.00, 29000.00]
    for idx, (d, c) in enumerate(zip(dias_atras, costos), start=7):
        f = ahora - timedelta(days=d)
        cur.execute(f"""
            INSERT INTO envios (id_envio, nro_guia, id_remitente, id_destinatario, id_localidad_destino, id_seguro, id_hoja_ruta, direccion_destino, valor_declarado, modalidad_pago, costo_total, estado_actual, es_devolucion, fecha_creacion)
            VALUES ({idx}, 'FP-2026-HIST0{idx}', 1, 2, 2, 1, 1, 'Zona Comercial', 40000.00, 'efectivo', {c}, 'entregado', 0, %s);
        """, (f,))
        cur.execute(f"INSERT INTO bultos (id_bulto, id_envio, peso_real, peso_volumetrico, es_fragil) VALUES ({idx+2}, {idx}, 5.0, 4.0, 0);")
        cur.execute(f"INSERT INTO pagos (id_pago, id_envio, id_turno, monto, fecha, tipo_pago, monto_entregado) VALUES ({idx}, {idx}, 1, {c}, %s, 'efectivo', {c});", (f,))
        cur.execute(f"INSERT INTO historial_estados (id_envio, fecha_hora, estado, ubicacion, observacion) VALUES ({idx}, %s, 'entregado', 'Destino', 'Entregado en fecha histórica');", (f,))

    print("  [OK] Envíos de prueba, bultos, pagos y comprobantes cargados.")


def seed_soporte(cur):
    """Carga una consulta de soporte en vivo pendiente para la demo."""
    ahora = datetime.now()
    cur.execute("""
        INSERT INTO chats_soporte (id_chat, session_id, cliente_nombre, cliente_email, nro_guia, estado, id_usuario_atendiendo, nombre_usuario_atendiendo, fecha_creacion, fecha_actualizacion)
        VALUES (1, 'demo-session-roberto-2026', 'Roberto Fernández', 'rfernandez@yahoo.com', 'FP-84920182', 'sin_atender', NULL, NULL, %s, %s);
    """, (ahora - timedelta(minutes=12), ahora - timedelta(minutes=12)))

    cur.execute("""
        INSERT INTO mensajes_soporte (id_mensaje, id_chat, remitente_tipo, remitente_nombre, mensaje, fecha_envio)
        VALUES (1, 1, 'cliente', 'Roberto Fernández', 'Hola buenas tardes, ¿a qué hora aproximadamente llega el móvil de reparto a Clorinda hoy? Saludos.', %s);
    """, (ahora - timedelta(minutes=12),))
    print("  [OK] Chat de soporte en espera cargado en bandeja de entrada.")


def main():
    print("=" * 60)
    print("  [FormoPack Express] — Carga de Datos Semilla para Demo")
    print("=" * 60)

    db = DatabaseManager.get_instance()
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)

    try:
        limpiar_tablas(cur)
        seed_usuarios(cur)
        seed_vehiculos(cur)
        seed_clientes(cur)
        seed_caja(cur)
        seed_hojas_y_envios(cur)
        seed_soporte(cur)

        conn.commit()
        print("\n" + "=" * 60)
        print("  ¡ÉXITO! Base de datos poblada para la demostración.")
        print("=" * 60)
        print("  Credenciales de acceso:")
        print("    Admin:       admin@formopack.com       / admin123")
        print("    Recepcionista: recepcion@formopack.com / recep456")
        print("    Chofer:      chofer@formopack.com      / chofer789")
        print("\n  Envíos clave para la exposición:")
        print("    FP-84920181 -> Entregado con firma digital (POD) y GPS.")
        print("    FP-84920182 -> En Ruta (¡Abre el mapa Leaflet en vivo y la PWA del chofer!).")
        print("    FP-84920184 -> En Custodia (3 visitas fallidas -> Credencial de Retiro).")
        print("    FP-84920185 -> Recibido en depósito (Listo para armar despacho en vivo).")
        print("    FP-84920186 -> Multibulto frágil (Regla 100%/50% y +10%).")
        print("=" * 60 + "\n")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Falló la carga de semillas: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
