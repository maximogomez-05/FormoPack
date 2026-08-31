"""
Rutas de Administración — Dashboard, Tracking
Blueprint: admin_bp
"""

import logging
from flask import Blueprint, render_template, session, request, jsonify
from web.routes.auth import login_required, rol_requerido
from app.core.database import DatabaseManager
from app.utils.exceptions import DatabaseConnectionError, DatabaseQueryError

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


@admin_bp.route("/dashboard")
@login_required
@rol_requerido("administrador", "recepcionista")
def dashboard():
    """Dashboard principal con métricas del día."""
    metricas = _obtener_metricas()
    ultimos_envios = _obtener_ultimos_envios(limite=10)
    return render_template(
        "admin/dashboard.html",
        metricas=metricas,
        ultimos_envios=ultimos_envios,
    )


@admin_bp.route("/tracking", methods=["GET"])
def tracking_publico():
    """Tracking público: consulta por número de guía (sin login)."""
    nro_guia = request.args.get("guia", "").strip().upper()
    timeline = []
    envio = None
    error = None

    if nro_guia:
        try:
            envio, timeline = _obtener_timeline(nro_guia)
            if not envio:
                error = f"No se encontró ningún envío con la guía '{nro_guia}'."
        except DatabaseConnectionError:
            error = "No se puede conectar a la base de datos."
        except Exception as e:
            logger.error("Error en tracking: %s", e)
            error = "Ocurrió un error al consultar el envío."

    return render_template(
        "tracking.html",
        nro_guia=nro_guia,
        envio=envio,
        timeline=timeline,
        error=error,
    )


# ──────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────
def _obtener_metricas() -> dict:
    """Obtiene métricas del día desde la BD."""
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Envíos de hoy
        cursor.execute("""
            SELECT
                COUNT(*) AS total_envios,
                COALESCE(SUM(costo_total), 0) AS facturado_total,
                SUM(CASE WHEN estado_actual = 'recibido' THEN 1 ELSE 0 END) AS recibidos,
                SUM(CASE WHEN estado_actual = 'entregado' THEN 1 ELSE 0 END) AS entregados
            FROM envios
            WHERE DATE(fecha_creacion) = CURDATE()
        """)
        metricas = cursor.fetchone() or {}

        # Caja del día
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN tipo_pago = 'efectivo' THEN monto ELSE 0 END), 0) AS efectivo_hoy,
                COALESCE(SUM(CASE WHEN tipo_pago = 'digital' THEN monto ELSE 0 END), 0) AS digital_hoy,
                COUNT(*) AS pagos_hoy
            FROM pagos
            WHERE DATE(fecha) = CURDATE()
        """)
        caja = cursor.fetchone() or {}

        cursor.close()
        conn.close()

        return {
            "total_envios": int(metricas.get("total_envios", 0)),
            "facturado_total": float(metricas.get("facturado_total", 0)),
            "recibidos": int(metricas.get("recibidos", 0)),
            "entregados": int(metricas.get("entregados", 0)),
            "efectivo_hoy": float(caja.get("efectivo_hoy", 0)),
            "digital_hoy": float(caja.get("digital_hoy", 0)),
            "pagos_hoy": int(caja.get("pagos_hoy", 0)),
        }
    except Exception as e:
        logger.error("Error al obtener métricas: %s", e)
        return {
            "total_envios": 0, "facturado_total": 0,
            "recibidos": 0, "entregados": 0,
            "efectivo_hoy": 0, "digital_hoy": 0, "pagos_hoy": 0,
        }


def _obtener_ultimos_envios(limite: int = 10) -> list:
    """Obtiene los últimos envíos registrados."""
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                e.nro_guia,
                e.estado_actual,
                e.costo_total,
                e.modalidad_pago,
                e.fecha_creacion,
                cr.nombre_completo AS remitente,
                cd.nombre_completo AS destinatario,
                l.nombre AS localidad_destino
            FROM envios e
            JOIN clientes cr ON e.id_remitente = cr.id_cliente
            JOIN clientes cd ON e.id_destinatario = cd.id_cliente
            JOIN localidades l ON e.id_localidad_destino = l.id_localidad
            ORDER BY e.fecha_creacion DESC
            LIMIT %s
        """, (limite,))
        filas = cursor.fetchall()
        cursor.close()
        conn.close()
        return filas
    except Exception as e:
        logger.error("Error al obtener envíos: %s", e)
        return []


def _obtener_timeline(nro_guia: str):
    """Obtiene el envío y su timeline de estados."""
    db = DatabaseManager.get_instance()
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            e.*,
            cr.nombre_completo AS remitente,
            cd.nombre_completo AS destinatario,
            l.nombre AS localidad_destino
        FROM envios e
        JOIN clientes cr ON e.id_remitente = cr.id_cliente
        JOIN clientes cd ON e.id_destinatario = cd.id_cliente
        JOIN localidades l ON e.id_localidad_destino = l.id_localidad
        WHERE e.nro_guia = %s
    """, (nro_guia,))
    envio = cursor.fetchone()

    timeline = []
    if envio:
        cursor.execute("""
            SELECT estado, fecha_hora, ubicacion, observacion
            FROM historial_estados
            WHERE id_envio = %s
            ORDER BY fecha_hora ASC
        """, (envio["id_envio"],))
        timeline = cursor.fetchall()

    cursor.close()
    conn.close()
    return envio, timeline
