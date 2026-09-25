"""
Rutas de Administración — Dashboard, Tracking
Blueprint: admin_bp
"""

import logging
import csv
import io
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Blueprint, Response, render_template, session, request, jsonify, redirect, url_for, flash
from web.routes.auth import login_required, rol_requerido
from app.core.database import DatabaseManager
from app.models.vehiculo import Vehiculo
from app.models.hoja_ruta import HojaRuta
from app.controllers.logistica_controller import LogisticaController
from app.utils.exceptions import DatabaseConnectionError, DatabaseQueryError, ValidationError, DuplicateError
from app.controllers.usuario_controller import UsuarioController
from config.settings import EmailConfig
admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


@admin_bp.route("/dashboard")
@login_required
@rol_requerido("administrador", "recepcionista")
def dashboard():
    """Dashboard principal con métricas del día."""
    metricas = _obtener_metricas()
    historico = _obtener_historico_metricas()
    ultimos_envios = _obtener_ultimos_envios(limite=10)
    alertas = construir_alertas_operativas(ultimos_envios)
    return render_template(
        "admin/dashboard.html",
        metricas=metricas,
        historico=historico,
        ultimos_envios=ultimos_envios,
        alertas=alertas,
    )


@admin_bp.route("/reportes/envios.csv", methods=["GET"])
@login_required
@rol_requerido("administrador", "recepcionista")
def descargar_reporte_envios():
    """Exporta un reporte operativo de envíos en formato CSV (RF 5.4)."""
    fecha_desde = request.args.get("desde", "").strip()
    fecha_hasta = request.args.get("hasta", "").strip()
    try:
        desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date() if fecha_desde else datetime.now().date() - timedelta(days=6)
        hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date() if fecha_hasta else datetime.now().date()
    except ValueError:
        return Response("Las fechas deben tener formato AAAA-MM-DD.\n", status=400, mimetype="text/plain")
    if desde > hasta:
        return Response("La fecha inicial no puede ser posterior a la fecha final.\n", status=400, mimetype="text/plain")

    filas = _obtener_reporte_envios(desde, hasta)
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    escritor.writerow(["Guia", "Estado", "Remitente", "Destinatario", "Destino", "Costo", "Modalidad de pago", "Fecha de creacion"])
    for fila in filas:
        escritor.writerow([
            fila.get("nro_guia", ""), fila.get("estado_actual", ""),
            fila.get("remitente", ""), fila.get("destinatario", ""),
            fila.get("localidad_destino", ""), fila.get("costo_total", 0),
            fila.get("modalidad_pago", ""), fila.get("fecha_creacion", ""),
        ])
    respuesta = Response("\ufeff" + salida.getvalue(), mimetype="text/csv; charset=utf-8")
    respuesta.headers["Content-Disposition"] = f"attachment; filename=reporte_envios_{desde}_{hasta}.csv"
    return respuesta


@admin_bp.route("/alertas/email", methods=["POST"])
@login_required
@rol_requerido("administrador")
def enviar_alertas_email():
    """Envía por Gmail las alertas operativas actuales (RF 5.5)."""
    alertas = construir_alertas_operativas(_obtener_ultimos_envios(limite=50))
    if not alertas:
        flash("No hay alertas pendientes para enviar.", "info")
        return redirect(url_for("admin.dashboard"))
    try:
        _enviar_alertas_gmail(alertas)
        flash("Las alertas fueron enviadas por Gmail correctamente.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    except (OSError, smtplib.SMTPException) as e:
        logger.error("Error al enviar alertas por Gmail: %s", e)
        flash("No se pudieron enviar las alertas por Gmail.", "danger")
    return redirect(url_for("admin.dashboard"))


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
        # Obtener vehículos disponibles
        vehiculos = logistica_ctrl.listar_vehiculos()

        # Obtener entregas en espera de despacho
        entregas_pendientes = logistica_ctrl.obtener_entregas_pendientes(estado="recibido")

        # Ordenar por distancia (ruteo óptimo)
        entregas_ordenadas = logistica_ctrl.sugerir_ruta_optima(entregas_pendientes)
        total_km = sum(float(e.get("distancia_km", 0.0)) for e in entregas_ordenadas)

        # Obtener hojas de ruta activas
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
        choferes=_obtener_choferes_disponibles(),
        total_km=total_km,
        error=error,
    )


@admin_bp.route("/logistica/vehiculos/nuevo", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def registrar_vehiculo():
    """Registra un vehículo disponible desde la pantalla de logística."""
    try:
        LogisticaController().registrar_vehiculo(
            request.form.get("patente", ""),
            float(request.form.get("capacidad_kg", 0)),
        )
        flash("Vehículo registrado correctamente.", "success")
    except ValueError:
        flash("La capacidad debe ser un número válido.", "danger")
    except Exception as e:
        logger.error("Error al registrar vehículo: %s", e)
        flash(str(e), "danger")
    return redirect(url_for("admin.logistica"))


@admin_bp.route("/logistica/hojas/nueva", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def crear_hoja_ruta():
    """Crea una hoja de ruta con envíos recibidos."""
    envios_ids = request.form.getlist('envios_ids')
    if not envios_ids:
        flash('Debe seleccionar al menos un envío para crear la hoja de ruta.', 'warning')
        return redirect(url_for('admin.logistica'))
    try:
        envios_ids = [int(value) for value in envios_ids]
        LogisticaController().crear_hoja_ruta(
            request.form.get("nro_despacho", "").strip(),
            int(request.form.get("id_chofer", 0)),
            int(request.form.get("id_vehiculo", 0)),
            envios_ids,
        )
        flash("Hoja de ruta creada y envíos asignados correctamente.", "success")
    except (ValueError, TypeError):
        flash("Completá correctamente los datos de la hoja de ruta.", "danger")
    except Exception as e:
        logger.error("Error al crear hoja de ruta: %s", e)
        flash(str(e), "danger")
    return redirect(url_for("admin.logistica"))


def _obtener_choferes_disponibles() -> list:
    """Obtiene choferes activos para asignar un despacho."""
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT id_usuario, nombre FROM usuarios
               WHERE tipo_usuario = 'chofer' AND activo = 1 ORDER BY nombre"""
        )
        choferes = cursor.fetchall()
        cursor.close()
        conn.close()
        return choferes
    except Exception as e:
        logger.error("Error al obtener choferes: %s", e)
        return []


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
            timeline = construir_timeline(envio, timeline)
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

@admin_bp.route('/usuarios')
@login_required  
@rol_requerido('administrador')
def usuarios():
    ctrl = UsuarioController()
    lista = ctrl.listar_usuarios()
    return render_template('admin/usuarios.html', usuarios=lista)

@admin_bp.route('/usuarios/nuevo', methods=['POST'])
@login_required
@rol_requerido('administrador')
def crear_usuario():
    try:
        ctrl = UsuarioController()
        nombre = request.form.get('nombre', '')
        email = request.form.get('email', '')
        tipo_usuario = request.form.get('tipo_usuario', '')
        password = request.form.get('password', '')
        
        ctrl.crear_usuario(nombre, email, tipo_usuario, password)
        flash("Usuario creado exitosamente.", "success")
    except DuplicateError as e:
        flash(str(e), "danger")
    except ValidationError as e:
        flash(str(e), "danger")
    except Exception as e:
        logger.error("Error al crear usuario: %s", e)
        flash("Ocurrió un error al crear el usuario.", "danger")
        
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/usuarios/<int:id_usuario>/toggle', methods=['POST'])
@login_required
@rol_requerido('administrador')
def toggle_usuario(id_usuario: int):
    try:
        ctrl = UsuarioController()
        id_solicitante = session.get('usuario_id')
        nuevo_estado = ctrl.toggle_activo(id_usuario, id_solicitante)
        
        estado_str = "activado" if nuevo_estado else "desactivado"
        flash(f"Usuario {estado_str} exitosamente.", "success")
    except ValidationError as e:
        flash(str(e), "danger")
    except Exception as e:
        logger.error("Error al cambiar estado de usuario: %s", e)
        flash("Ocurrió un error al cambiar el estado del usuario.", "danger")
        
    return redirect(url_for('admin.usuarios'))


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
                COALESCE(SUM(CASE WHEN estado_actual = 'recibido' THEN 1 ELSE 0 END), 0) AS recibidos,
                COALESCE(SUM(CASE WHEN estado_actual = 'entregado' THEN 1 ELSE 0 END), 0) AS entregados,
                COALESCE(SUM(CASE WHEN estado_actual = 'fallido' THEN 1 ELSE 0 END), 0) AS fallidos,
                COALESCE(SUM(CASE WHEN estado_actual = 'en_ruta' THEN 1 ELSE 0 END), 0) AS en_ruta
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
            "fallidos": int(metricas.get("fallidos", 0)),
            "en_ruta": int(metricas.get("en_ruta", 0)),
            "efectivo_hoy": float(caja.get("efectivo_hoy", 0)),
            "digital_hoy": float(caja.get("digital_hoy", 0)),
            "pagos_hoy": int(caja.get("pagos_hoy", 0)),
        }
    except Exception as e:
        logger.error("Error al obtener métricas: %s", e)
        return {
            "total_envios": 0, "facturado_total": 0,
            "recibidos": 0, "entregados": 0, "fallidos": 0, "en_ruta": 0,
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


def _obtener_reporte_envios(desde, hasta) -> list:
    """Obtiene el detalle de envíos para el reporte operativo."""
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                e.nro_guia, e.estado_actual, e.costo_total, e.modalidad_pago,
                e.fecha_creacion,
                cr.nombre_completo AS remitente,
                cd.nombre_completo AS destinatario,
                l.nombre AS localidad_destino
            FROM envios e
            JOIN clientes cr ON e.id_remitente = cr.id_cliente
            JOIN clientes cd ON e.id_destinatario = cd.id_cliente
            JOIN localidades l ON e.id_localidad_destino = l.id_localidad
            WHERE DATE(e.fecha_creacion) BETWEEN %s AND %s
            ORDER BY e.fecha_creacion ASC
        """, (desde, hasta))
        filas = cursor.fetchall()
        cursor.close()
        conn.close()
        return filas
    except Exception as e:
        logger.error("Error al generar reporte de envíos: %s", e)
        return []


def construir_alertas_operativas(envios: list[dict], ahora=None) -> list[dict]:
    """Construye alertas locales para supervisar envíos demorados o fallidos (RF 5.5)."""
    ahora = ahora or datetime.now()
    alertas = []
    for envio in envios or []:
        estado = str(envio.get("estado_actual") or "").lower()
        guia = envio.get("nro_guia") or "Sin guía"
        fecha = envio.get("fecha_creacion")
        if isinstance(fecha, str):
            try:
                fecha = datetime.fromisoformat(fecha)
            except ValueError:
                fecha = None

        if estado == "fallido":
            alertas.append({"tipo": "danger", "guia": guia, "mensaje": "Entrega fallida: requiere seguimiento."})
        elif estado == "recibido" and fecha and ahora - fecha >= timedelta(hours=24):
            alertas.append({"tipo": "warning", "guia": guia, "mensaje": "Envío recibido hace más de 24 horas sin despacho."})
        elif estado == "en_ruta" and fecha and ahora - fecha >= timedelta(days=2):
            alertas.append({"tipo": "warning", "guia": guia, "mensaje": "Envío en ruta hace más de 48 horas: revisar estado."})
    return alertas


def _enviar_alertas_gmail(alertas: list[dict]) -> None:
    """Envía un resumen de alertas mediante una cuenta Gmail con contraseña de aplicación."""
    if not EmailConfig.USER or not EmailConfig.PASSWORD or not EmailConfig.RECIPIENT:
        raise ValueError("Configurá GMAIL_USER, GMAIL_APP_PASSWORD y ALERTAS_EMAIL para enviar alertas.")

    mensaje = EmailMessage()
    mensaje["Subject"] = f"FormoPack: {len(alertas)} alerta(s) operativa(s)"
    mensaje["From"] = EmailConfig.USER
    mensaje["To"] = EmailConfig.RECIPIENT
    cuerpo = ["Se detectaron las siguientes alertas en FormoPack:", ""]
    cuerpo.extend(f"- {alerta['guia']}: {alerta['mensaje']}" for alerta in alertas)
    mensaje.set_content("\n".join(cuerpo))

    with smtplib.SMTP_SSL(EmailConfig.HOST, EmailConfig.PORT, timeout=15) as smtp:
        smtp.login(EmailConfig.USER, EmailConfig.PASSWORD)
        smtp.send_message(mensaje)


def _obtener_historico_metricas() -> list:
    """Obtiene siete días de actividad para el dashboard gerencial."""
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                DATE(fecha_creacion) AS dia,
                COUNT(*) AS total_envios,
                COALESCE(SUM(CASE WHEN estado_actual = 'entregado' THEN 1 ELSE 0 END), 0) AS entregados,
                COALESCE(SUM(CASE WHEN estado_actual = 'fallido' THEN 1 ELSE 0 END), 0) AS fallidos,
                COALESCE(SUM(costo_total), 0) AS facturado
            FROM envios
            WHERE fecha_creacion >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
            GROUP BY DATE(fecha_creacion)
            ORDER BY dia ASC
        """)
        filas = cursor.fetchall()
        cursor.close()
        conn.close()
        return filas
    except Exception as e:
        logger.error("Error al obtener histórico del dashboard: %s", e)
        return []


def construir_timeline(envio: dict | None, historial: list[dict]) -> list[dict]:
    """Normaliza el historial para mostrar un timeline consistente en tracking público."""
    if not envio:
        return []

    eventos = []
    for item in historial or []:
        fecha_hora = item.get("fecha_hora") or item.get("fecha")
        if fecha_hora is None:
            continue
        eventos.append({
            "estado": str(item.get("estado") or envio.get("estado_actual") or "recibido").lower(),
            "fecha_hora": fecha_hora,
            "ubicacion": item.get("ubicacion") or "Sucursal Origen",
            "observacion": item.get("observacion") or "Movimiento registrado en sistema.",
        })

    if not eventos:
        eventos.append({
            "estado": str(envio.get("estado_actual") or "recibido").lower(),
            "fecha_hora": envio.get("fecha_creacion") or "2000-01-01 00:00:00",
            "ubicacion": "Sucursal Origen",
            "observacion": "Envío registrado en sistema.",
        })

    eventos.sort(key=lambda item: str(item["fecha_hora"]))
    return eventos


def construir_resumen_tracking(envio: dict | None, historial: list[dict]) -> dict:
    """Resumir el estado actual del envío para la vista pública."""
    if not envio:
        return {
            "estado": "no_encontrado",
            "ultima_actualizacion": None,
            "ubicacion_actual": "Sin información",
            "progreso": "sin_datos",
        }

    timeline = construir_timeline(envio, historial)
    estado_actual = str(envio.get("estado_actual") or timeline[-1].get("estado") or "recibido").lower()
    ultimo_evento = timeline[-1] if timeline else {
        "fecha_hora": envio.get("fecha_creacion") or "2000-01-01 00:00:00",
        "ubicacion": "Sucursal Origen",
    }

    if estado_actual == "entregado":
        progreso = "entregado"
    elif estado_actual == "fallido":
        progreso = "fallido"
    elif estado_actual in {"en_ruta", "en_planta"}:
        progreso = "en_tránsito"
    else:
        progreso = "registrado"

    return {
        "estado": estado_actual,
        "ultima_actualizacion": ultimo_evento.get("fecha_hora"),
        "ubicacion_actual": ultimo_evento.get("ubicacion") or "Sucursal Origen",
        "progreso": progreso,
    }


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
