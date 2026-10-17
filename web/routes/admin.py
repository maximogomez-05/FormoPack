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
from app.models.comprobante_interno import ComprobanteInterno
from app.controllers.logistica_controller import LogisticaController
from app.utils.exceptions import DatabaseConnectionError, DatabaseQueryError, ValidationError, DuplicateError
from app.controllers.usuario_controller import UsuarioController
from app.controllers.liquidacion_controller import LiquidacionController
from config.settings import EmailConfig
admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


def _mensaje_usuario_error(excepcion: Exception, fallback: str = "Ocurrió un error inesperado.") -> str:
    """Convierte excepciones internas en mensajes útiles para la UI."""
    if hasattr(excepcion, "message"):
        mensaje = str(excepcion.message)
    else:
        mensaje = str(excepcion)

    if isinstance(excepcion, ValidationError):
        return mensaje.replace("[VALIDATION_ERROR] ", "").replace("Validacion fallida en '", "").replace("': ", ": ").replace("'.", ".")

    texto = (mensaje or fallback).strip()
    texto_lower = texto.lower()

    if "duplicate entry" in texto_lower or "uk_" in texto_lower:
        return "Ya existe un registro con ese valor. Revisá la patente, la guía o el número de despacho."
    if "foreign key" in texto_lower or "cannot add or update a child row" in texto_lower:
        return "Hay un dato relacionado que no existe. Revisá chofer, vehículo o envío asociado."
    if "cannot be null" in texto_lower or "not null" in texto_lower:
        return "Faltan datos obligatorios para completar la operación."
    if "data too long" in texto_lower:
        return "Uno de los campos supera la longitud permitida. Revisá los datos ingresados."
    if "out of range" in texto_lower:
        return "Un valor numérico quedó fuera del rango permitido."
    if "unknown column" in texto_lower or "field list" in texto_lower or "no such column" in texto_lower:
        return "La base de datos está desactualizada: falta una columna del sistema. Actualizá la estructura de la base de datos o ejecutá el script de inicialización."

    return texto or fallback


@admin_bp.route("/dashboard")
@login_required
@rol_requerido("administrador", "recepcionista")
def dashboard():
    """Dashboard principal con métricas del día."""
    metricas = _obtener_metricas()
    historico = _obtener_historico_metricas()
    ultimos_envios = _obtener_ultimos_envios(limite=10)
    alertas = construir_alertas_operativas(_obtener_envios_para_alertas())
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
    estado = request.args.get("estado", "").strip().lower()
    try:
        desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date() if fecha_desde else datetime.now().date() - timedelta(days=6)
        hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date() if fecha_hasta else datetime.now().date()
    except ValueError:
        return Response("Las fechas deben tener formato AAAA-MM-DD.\n", status=400, mimetype="text/plain")
    if desde > hasta:
        return Response("La fecha inicial no puede ser posterior a la fecha final.\n", status=400, mimetype="text/plain")

    filas = _obtener_reporte_envios(desde, hasta, estado=estado or None)
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
    nombre_estado = f"_{estado}" if estado else ""
    respuesta.headers["Content-Disposition"] = f"attachment; filename=reporte_envios_{desde}_{hasta}{nombre_estado}.csv"
    return respuesta


@admin_bp.route("/alertas/email", methods=["POST"])
@login_required
@rol_requerido("administrador")
def enviar_alertas_email():
    """Envía por Gmail las alertas operativas actuales (RF 5.5)."""
    alertas = construir_alertas_operativas(_obtener_envios_para_alertas())
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
    except (ValidationError, DatabaseQueryError, DatabaseConnectionError, DuplicateError) as e:
        logger.error("Error al registrar vehículo: %s", e)
        flash(_mensaje_usuario_error(e, "No se pudo registrar el vehículo."), "danger")
    except Exception as e:
        logger.error("Error inesperado al registrar vehículo: %s", e)
        flash(_mensaje_usuario_error(e, "No se pudo registrar el vehículo."), "danger")
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
        flash("Completá correctamente los datos de la hoja de ruta. Revisá número de despacho, chofer, vehículo y envíos seleccionados.", "danger")
    except (ValidationError, DatabaseQueryError, DatabaseConnectionError, DuplicateError) as e:
        logger.error("Error al crear hoja de ruta: %s", e)
        flash(_mensaje_usuario_error(e, "No se pudo crear la hoja de ruta."), "danger")
    except Exception as e:
        logger.error("Error inesperado al crear hoja de ruta: %s", e)
        flash(_mensaje_usuario_error(e, "No se pudo crear la hoja de ruta."), "danger")
    return redirect(url_for("admin.logistica"))


def _obtener_choferes_disponibles() -> list:
    """Obtiene choferes activos para asignar un despacho."""
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT id_usuario, nombre FROM usuarios
               WHERE tipo_usuario = 'chofer' AND activo = 1 ORDER BY nombre"""
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error("Error al obtener choferes: %s", e)
        return []
    finally:
        if conn:
            conn.close()


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
# RF 5.6 — Liquidaciones de Choferes
# ──────────────────────────────────────────
@admin_bp.route('/liquidaciones')
@login_required
@rol_requerido('administrador')
def liquidaciones():
    """Liquidaciones de choferes — rendimiento y facturación por período."""
    from datetime import date

    liq_ctrl = LiquidacionController()
    choferes = liq_ctrl.obtener_choferes_con_actividad()

    # Parámetros de filtro
    id_chofer_sel = request.args.get('id_chofer', '').strip()
    fecha_desde_str = request.args.get('desde', '').strip()
    fecha_hasta_str = request.args.get('hasta', '').strip()

    # Valores por defecto: últimos 30 días
    hoy = date.today()
    try:
        fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date() if fecha_desde_str else hoy.replace(day=1)
        fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date() if fecha_hasta_str else hoy
    except ValueError:
        flash('Las fechas ingresadas no son válidas.', 'warning')
        fecha_desde = hoy.replace(day=1)
        fecha_hasta = hoy

    liquidacion = None
    resumen = None

    # Solo consultar si hay parámetros de fecha (no en carga inicial)
    if fecha_desde_str or fecha_hasta_str:
        try:
            if id_chofer_sel:
                # Liquidación individual
                liquidacion = liq_ctrl.generar_liquidacion(
                    int(id_chofer_sel), fecha_desde, fecha_hasta
                )
                if liquidacion and liquidacion.total_hojas == 0:
                    flash('No se encontraron hojas de ruta para este chofer en el período seleccionado.', 'info')
                    liquidacion = None
            else:
                # Resumen de todos
                resumen = liq_ctrl.generar_resumen_todos(fecha_desde, fecha_hasta)
                if not resumen:
                    flash('No se encontraron registros en el período seleccionado.', 'info')
        except ValidationError as e:
            flash(str(e), 'warning')
        except Exception as e:
            logger.error("Error al generar liquidación: %s", e)
            flash('Ocurrió un error al generar la liquidación.', 'danger')

    return render_template(
        'admin/liquidaciones.html',
        choferes=choferes,
        id_chofer_sel=id_chofer_sel,
        fecha_desde=fecha_desde.isoformat(),
        fecha_hasta=fecha_hasta.isoformat(),
        liquidacion=liquidacion,
        resumen=resumen,
    )


# ──────────────────────────────────────────
# RF 2.7 / Administración — Gestión y Consulta de Comprobantes de Servicios
# ──────────────────────────────────────────
@admin_bp.route("/comprobantes", methods=["GET"])
@login_required
@rol_requerido("administrador")
def comprobantes():
    """Sector administrativo para almacenar, consultar y auditar comprobantes de servicios."""
    filtros = {
        "q": request.args.get("q", "").strip(),
        "desde": request.args.get("desde", "").strip(),
        "hasta": request.args.get("hasta", "").strip(),
        "estado": request.args.get("estado", "").strip(),
        "modalidad": request.args.get("modalidad", "").strip(),
        "estado_pago": request.args.get("estado_pago", "").strip(),
    }

    comprobantes_lista = _obtener_comprobantes_admin(filtros)

    metricas = {
        "total_comprobantes": len(comprobantes_lista),
        "facturacion_total": sum(float(c.get("costo_total") or 0) for c in comprobantes_lista),
        "total_cobrado": sum(float(c.get("monto_pagado") or 0) for c in comprobantes_lista if c.get("monto_pagado")),
        "total_pendientes": sum(1 for c in comprobantes_lista if not c.get("monto_pagado")),
    }

    estados_disponibles = [
        {"codigo": "recibido", "nombre": "Recibido"},
        {"codigo": "en_planta", "nombre": "En Planta"},
        {"codigo": "en_ruta", "nombre": "En Ruta"},
        {"codigo": "entregado", "nombre": "Entregado"},
        {"codigo": "fallido", "nombre": "Fallido"},
        {"codigo": "devolucion", "nombre": "Devolución"},
        {"codigo": "siniestro", "nombre": "Siniestro"},
    ]

    modalidades_disponibles = [
        {"codigo": "efectivo", "nombre": "Efectivo"},
        {"codigo": "digital", "nombre": "Digital (QR/MP)"},
        {"codigo": "cuenta_corriente", "nombre": "Cuenta Corriente"},
    ]

    return render_template(
        "admin/comprobantes.html",
        comprobantes=comprobantes_lista,
        metricas=metricas,
        filtros=filtros,
        estados_disponibles=estados_disponibles,
        modalidades_disponibles=modalidades_disponibles,
    )


@admin_bp.route("/comprobantes/exportar.csv", methods=["GET"])
@login_required
@rol_requerido("administrador")
def exportar_comprobantes_csv():
    """Exporta los comprobantes consultados a CSV con codificación UTF-8 BOM."""
    filtros = {
        "q": request.args.get("q", "").strip(),
        "desde": request.args.get("desde", "").strip(),
        "hasta": request.args.get("hasta", "").strip(),
        "estado": request.args.get("estado", "").strip(),
        "modalidad": request.args.get("modalidad", "").strip(),
        "estado_pago": request.args.get("estado_pago", "").strip(),
    }

    filas = _obtener_comprobantes_admin(filtros)
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    escritor.writerow([
        "Nro Comprobante",
        "Nro Guia",
        "Fecha Emision",
        "Remitente",
        "DNI Remitente",
        "Telefono Remitente",
        "Destinatario",
        "DNI Destinatario",
        "Telefono Destinatario",
        "Localidad Destino",
        "Direccion Destino",
        "Bultos",
        "Peso Aforado Total (kg)",
        "Subtotal Flete ($)",
        "Seguro ($)",
        "Costo Total ($)",
        "Modalidad Pago",
        "Estado Pago",
        "Monto Cobrado ($)",
        "Medio Pago",
        "Fecha Pago",
        "Estado Envio",
    ])

    for f in filas:
        fe = f.get("fecha_emision")
        fe_str = fe.strftime("%d/%m/%Y %H:%M") if hasattr(fe, "strftime") else str(fe or "")
        fp = f.get("fecha_pago")
        fp_str = fp.strftime("%d/%m/%Y %H:%M") if hasattr(fp, "strftime") else str(fp or "")
        estado_pago_txt = "Pagado" if f.get("monto_pagado") is not None else "Pendiente"

        escritor.writerow([
            f.get("nro_comprobante", ""),
            f.get("nro_guia", ""),
            fe_str,
            f.get("remitente", ""),
            f.get("rem_dni", ""),
            f.get("rem_tel", ""),
            f.get("destinatario", ""),
            f.get("dest_dni", ""),
            f.get("dest_tel", ""),
            f.get("localidad_destino", ""),
            f.get("direccion_destino", ""),
            f.get("total_bultos", 1),
            f.get("peso_total", 0),
            f.get("subtotal_flete", 0),
            f.get("costo_seguro", 0),
            f.get("costo_total", 0),
            f.get("modalidad_pago", ""),
            estado_pago_txt,
            f.get("monto_pagado", 0) if f.get("monto_pagado") is not None else 0,
            f.get("tipo_pago", "") or "",
            fp_str,
            f.get("estado_actual", ""),
        ])

    respuesta = Response("\ufeff" + salida.getvalue(), mimetype="text/csv; charset=utf-8")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    respuesta.headers["Content-Disposition"] = f"attachment; filename=comprobantes_servicios_{timestamp}.csv"
    return respuesta


# ──────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────
def _obtener_metricas() -> dict:
    """Obtiene métricas del día desde la BD."""
    conn = None
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
    finally:
        if conn:
            conn.close()


def _obtener_ultimos_envios(limite: int = 10) -> list:
    """Obtiene los últimos envíos registrados."""
    conn = None
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
        return cursor.fetchall()
    except Exception as e:
        logger.error("Error al obtener envíos: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def _obtener_envios_para_alertas() -> list:
    """Trae todos los envíos con incidencias y la fecha de su último estado actual."""
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                e.nro_guia,
                e.estado_actual,
                e.fecha_creacion,
                COALESCE(
                    (SELECT MAX(h.fecha_hora)
                     FROM historial_estados h
                     WHERE h.id_envio = e.id_envio AND h.estado = e.estado_actual),
                    e.fecha_creacion
                ) AS fecha_estado,
                (SELECT COUNT(*) FROM intentos_entrega i WHERE i.id_envio = e.id_envio) AS cantidad_intentos,
                (SELECT i.motivo_fallo FROM intentos_entrega i
                 WHERE i.id_envio = e.id_envio AND i.tipo_intento = 'fallido'
                 ORDER BY i.fecha_hora DESC, i.id_intento DESC LIMIT 1) AS motivo_fallo
            FROM envios e
            WHERE e.estado_actual IN ('recibido', 'en_ruta', 'fallido')
            ORDER BY fecha_estado ASC
        """)
        return cursor.fetchall()
    except Exception as e:
        logger.error("Error al obtener envíos para alertas operativas: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def _obtener_reporte_envios(desde, hasta, estado: str | None = None) -> list:
    """Obtiene el detalle de envíos para el reporte operativo."""
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        if estado:
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
                  AND e.estado_actual = %s
                ORDER BY e.fecha_creacion ASC
            """, (desde, hasta, estado))
        else:
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
        return cursor.fetchall()
    except Exception as e:
        logger.error("Error al generar reporte de envíos: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def construir_alertas_operativas(envios: list[dict], ahora=None) -> list[dict]:
    """Construye alertas locales para supervisar envíos demorados o fallidos (RF 5.5)."""
    ahora = ahora or datetime.now()
    alertas = []
    for envio in envios or []:
        estado = str(envio.get("estado_actual") or "").lower()
        guia = envio.get("nro_guia") or "Sin guía"
        fecha = envio.get("fecha_estado") or envio.get("fecha_creacion")
        if isinstance(fecha, str):
            try:
                fecha = datetime.fromisoformat(fecha)
            except ValueError:
                fecha = None

        if estado == "fallido":
            cantidad_intentos = int(envio.get("cantidad_intentos") or 0)
            motivo = str(envio.get("motivo_fallo") or "").replace("_", " ").strip().capitalize()
            detalle = f" Motivo: {motivo}." if motivo else ""
            alertas.append({
                "tipo": "danger",
                "guia": guia,
                "mensaje": f"Entrega fallida tras {cantidad_intentos} intento(s): requiere reintento o devolución.{detalle}",
            })
        elif estado == "recibido" and fecha and ahora - fecha >= timedelta(hours=24):
            alertas.append({"tipo": "warning", "guia": guia, "mensaje": "Envío recibido hace más de 24 horas sin despacho."})
        elif estado == "en_ruta" and fecha and ahora - fecha >= timedelta(days=2):
            alertas.append({"tipo": "warning", "guia": guia, "mensaje": "Envío en ruta hace más de 48 horas: revisar estado."})
    return alertas


def _obtener_destinatarios_alertas() -> list[str]:
    """Devuelve una lista de emails válidos para alertas operativas."""
    raw = (EmailConfig.RECIPIENT or "").replace(";", ",")
    return [email.strip() for email in raw.split(",") if email.strip()]


def _enviar_alertas_gmail(alertas: list[dict]) -> None:
    """Envía un resumen de alertas mediante una cuenta Gmail con contraseña de aplicación."""
    destinatarios = _obtener_destinatarios_alertas()
    if not EmailConfig.USER or not EmailConfig.PASSWORD or not destinatarios:
        raise ValueError("Completá GMAIL_USER, GMAIL_APP_PASSWORD y ALERTAS_EMAIL en el archivo .env. GMAIL_APP_PASSWORD debe ser una contraseña de aplicación de Google.")

    mensaje = EmailMessage()
    mensaje["Subject"] = f"FormoPack: {len(alertas)} alerta(s) operativa(s)"
    mensaje["From"] = EmailConfig.USER
    mensaje["To"] = ", ".join(destinatarios)
    cuerpo = ["Se detectaron las siguientes alertas en FormoPack:", ""]
    cuerpo.extend(f"- {alerta['guia']}: {alerta['mensaje']}" for alerta in alertas)
    mensaje.set_content("\n".join(cuerpo))

    with smtplib.SMTP_SSL(EmailConfig.HOST, EmailConfig.PORT, timeout=15) as smtp:
        smtp.login(EmailConfig.USER, EmailConfig.PASSWORD)
        smtp.send_message(mensaje)


def _obtener_historico_metricas() -> list:
    """Obtiene siete días de actividad para el dashboard gerencial."""
    conn = None
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
        return cursor.fetchall()
    except Exception as e:
        logger.error("Error al obtener histórico del dashboard: %s", e)
        return []
    finally:
        if conn:
            conn.close()


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
    conn = None
    try:
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

        historial = []
        if envio:
            cursor.execute("""
                SELECT * FROM historial_estados
                WHERE id_envio = %s
                ORDER BY fecha_hora ASC
            """, (envio["id_envio"],))
            historial = cursor.fetchall()

        return envio, historial
    except Exception as e:
        logger.error("Error al obtener timeline: %s", e)
        return None, []
    finally:
        if conn:
            conn.close()


def _obtener_comprobantes_admin(filtros: dict) -> list[dict]:
    """Recupera los comprobantes de servicios con filtros avanzados y sincronización automática."""
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Asegurar sincronización retroactiva de comprobantes para envíos previos
        try:
            cursor.execute("""
                INSERT IGNORE INTO comprobantes_internos (id_envio, nro_comprobante, tipo_comprobante, fecha_emision)
                SELECT
                    e.id_envio,
                    CONCAT('REC-', LPAD(e.id_envio, 6, '0'), '-', DATE_FORMAT(COALESCE(e.fecha_creacion, NOW()), '%Y%m%d')),
                    'recepcion',
                    COALESCE(e.fecha_creacion, NOW())
                FROM envios e
                LEFT JOIN comprobantes_internos c ON e.id_envio = c.id_envio AND c.tipo_comprobante = 'recepcion'
                WHERE c.id_comprobante IS NULL
            """)
            conn.commit()
        except Exception as err:
            logger.warning("Auto-sync de comprobantes omitido o fallido: %s", err)

        # 2. Query de comprobantes con datos de envío, partes y pagos
        sql = """
            SELECT
                c.id_comprobante,
                c.nro_comprobante,
                c.tipo_comprobante,
                c.fecha_emision,
                e.id_envio,
                e.nro_guia,
                e.estado_actual,
                e.costo_total,
                e.modalidad_pago,
                e.valor_declarado,
                e.direccion_destino,
                e.fecha_creacion,
                COALESCE(cr.nombre_completo, 'Desconocido') AS remitente,
                COALESCE(cr.dni, '—') AS rem_dni,
                COALESCE(cr.telefono, '—') AS rem_tel,
                COALESCE(cd.nombre_completo, 'Desconocido') AS destinatario,
                COALESCE(cd.dni, '—') AS dest_dni,
                COALESCE(cd.telefono, '—') AS dest_tel,
                COALESCE(ld.nombre, 'Sin destino') AS localidad_destino,
                s.cobertura_estandar,
                s.porcentaje_excedente,
                COALESCE((SELECT COUNT(*) FROM bultos b WHERE b.id_envio = e.id_envio), 0) AS total_bultos,
                COALESCE((SELECT SUM(GREATEST(COALESCE(b.peso_real, 0), COALESCE(b.peso_volumetrico, 0))) FROM bultos b WHERE b.id_envio = e.id_envio), 0) AS peso_total,
                (SELECT p.monto FROM pagos p WHERE p.id_envio = e.id_envio ORDER BY p.fecha DESC LIMIT 1) AS monto_pagado,
                (SELECT p.tipo_pago FROM pagos p WHERE p.id_envio = e.id_envio ORDER BY p.fecha DESC LIMIT 1) AS tipo_pago,
                (SELECT p.fecha FROM pagos p WHERE p.id_envio = e.id_envio ORDER BY p.fecha DESC LIMIT 1) AS fecha_pago
            FROM comprobantes_internos c
            JOIN envios e ON c.id_envio = e.id_envio
            LEFT JOIN clientes cr ON e.id_remitente = cr.id_cliente
            LEFT JOIN clientes cd ON e.id_destinatario = cd.id_cliente
            LEFT JOIN localidades ld ON e.id_localidad_destino = ld.id_localidad
            LEFT JOIN seguros s ON e.id_seguro = s.id_seguro
            WHERE 1=1
        """
        params = []

        q = (filtros.get("q") or "").strip()
        if q:
            sql += """
                AND (
                    c.nro_comprobante LIKE %s
                    OR e.nro_guia LIKE %s
                    OR cr.nombre_completo LIKE %s
                    OR cr.dni LIKE %s
                    OR cd.nombre_completo LIKE %s
                    OR cd.dni LIKE %s
                )
            """
            pq = f"%{q}%"
            params.extend([pq, pq, pq, pq, pq, pq])

        desde = (filtros.get("desde") or "").strip()
        if desde:
            sql += " AND DATE(c.fecha_emision) >= %s"
            params.append(desde)

        hasta = (filtros.get("hasta") or "").strip()
        if hasta:
            sql += " AND DATE(c.fecha_emision) <= %s"
            params.append(hasta)

        estado = (filtros.get("estado") or "").strip()
        if estado:
            sql += " AND e.estado_actual = %s"
            params.append(estado)

        modalidad = (filtros.get("modalidad") or "").strip()
        if modalidad:
            sql += " AND e.modalidad_pago = %s"
            params.append(modalidad)

        estado_pago = (filtros.get("estado_pago") or "").strip()
        if estado_pago == "pagado":
            sql += " AND EXISTS (SELECT 1 FROM pagos p WHERE p.id_envio = e.id_envio)"
        elif estado_pago == "pendiente":
            sql += " AND NOT EXISTS (SELECT 1 FROM pagos p WHERE p.id_envio = e.id_envio)"

        sql += " ORDER BY c.fecha_emision DESC, c.id_comprobante DESC"

        cursor.execute(sql, tuple(params))
        filas = cursor.fetchall() or []

        for f in filas:
            vd = float(f.get("valor_declarado") or 0)
            costo_total = float(f.get("costo_total") or 0)
            cob = f.get("cobertura_estandar")
            pct = f.get("porcentaje_excedente")
            if cob is not None and pct is not None:
                cob_val = float(cob)
                pct_val = float(pct)
                if vd > cob_val:
                    costo_seg = round((vd - cob_val) * (pct_val / 100.0), 2)
                else:
                    costo_seg = 0.0
            else:
                costo_seg = 0.0

            f["costo_seguro"] = costo_seg
            f["subtotal_flete"] = round(max(0.0, costo_total - costo_seg), 2)
            f["esta_pagado"] = f.get("monto_pagado") is not None

        return filas
    except Exception as e:
        logger.error("Error al obtener comprobantes de administración: %s", e)
        return []
    finally:
        if conn:
            conn.close()
