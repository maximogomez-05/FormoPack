"""
Rutas de Recepción — Cotizador, Nuevo Envío, Cobro, Caja
Blueprint: recepcion_bp
"""

import io
import logging
import qrcode
import base64
from datetime import datetime
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, jsonify, send_file,
)

from web.routes.auth import login_required, rol_requerido
from app.controllers.cliente_controller import ClienteController
from app.controllers.envio_controller import EnvioController
from app.controllers.caja_controller import CajaController
from app.core.database import DatabaseManager
from app.utils.exceptions import (
    ValidationError, DuplicateError, DatabaseConnectionError,
    DatabaseQueryError, ClienteNotFoundError, EnvioNotFoundError,
    TurnoCajaError, CotizacionError,
)
from app.services.cotizador import Cotizador
from app.models.bulto import Bulto
from app.models.solicitud_recepcion import SolicitudRecepcion
from app.services.validacion_entrada import ValidacionEntrada as V
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from app.models.pago import PagoDigital
from app.models.comprobante_interno import ComprobanteInterno
from app.services.mercadopago_service import MercadoPagoService
from config.settings import MercadoPagoConfig

recepcion_bp = Blueprint("recepcion", __name__)
logger = logging.getLogger(__name__)


def _mensaje_usuario_error(excepcion: Exception, fallback: str = "Ocurrió un error inesperado.") -> str:
    """Convierte errores internos en mensajes útiles para la UI."""
    if hasattr(excepcion, "message"):
        mensaje = str(excepcion.message)
    else:
        mensaje = str(excepcion)

    texto = (mensaje or fallback).strip()
    texto_lower = texto.lower()

    if isinstance(excepcion, ValidationError):
        return texto.replace("[VALIDATION_ERROR] ", "").replace("Validacion fallida en '", "").replace("': ", ": ").replace("'.", ".")

    if "duplicate entry" in texto_lower or "uk_" in texto_lower:
        return "Ya existe un registro con ese valor. Revisá la guía, el DNI, la patente o el número asociado."
    if "foreign key" in texto_lower or "cannot add or update a child row" in texto_lower:
        return "Hay un dato relacionado que no existe. Revisá el cliente, la localidad o el seguro seleccionado."
    if "cannot be null" in texto_lower or "not null" in texto_lower:
        return "Faltan datos obligatorios para completar el envío."
    if "data too long" in texto_lower:
        return "Uno de los campos supera la longitud permitida. Revisá los valores ingresados."
    if "out of range" in texto_lower:
        return "Un valor numérico quedó fuera del rango permitido."
    if "unknown column" in texto_lower or "field list" in texto_lower or "no such column" in texto_lower:
        return fallback

    if isinstance(excepcion, (CotizacionError, TurnoCajaError, DuplicateError)):
        return texto
    return fallback


# ──────────────────────────────────────────
# Inicio del módulo de recepción
# ──────────────────────────────────────────
@recepcion_bp.route("/")
@login_required
@rol_requerido("administrador", "recepcionista")
def inicio():
    """Panel principal de recepción."""
    return redirect(url_for("recepcion.cotizador"))


# ──────────────────────────────────────────
# RF 2.1 — Clientes
# ──────────────────────────────────────────
@recepcion_bp.route("/clientes")
@login_required
@rol_requerido("administrador", "recepcionista")
def listar_clientes():
    """Lista de clientes registrados."""
    ctrl = ClienteController()
    clientes = ctrl.listar_clientes(limite=100)
    return render_template("recepcion/clientes.html", clientes=clientes)


@recepcion_bp.route("/clientes/buscar")
@login_required
@rol_requerido("administrador", "recepcionista")
def buscar_cliente_ajax():
    """Búsqueda AJAX de cliente por DNI (para autocompletar en formularios)."""
    dni = request.args.get("dni", "").strip()
    if not dni:
        return jsonify({"encontrado": False})
    try:
        ctrl = ClienteController()
        cliente = ctrl.buscar_por_dni(dni)
        if cliente:
            return jsonify({"encontrado": True, "cliente": cliente.to_dict()})
        return jsonify({"encontrado": False})
    except ValidationError as e:
        return jsonify(encontrado=False, error=_mensaje_usuario_error(e)), 400
    except (DatabaseConnectionError, DatabaseQueryError):
        logger.exception("No se pudo buscar el cliente")
        return jsonify(encontrado=False, error="No se pudo consultar el cliente. Intentá nuevamente."), 503



@recepcion_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def nuevo_cliente():
    """Registro de un nuevo cliente."""
    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        nombre = request.form.get("nombre_completo", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip() or None
        try:
            ctrl = ClienteController()
            cliente = ctrl.registrar_cliente(dni, nombre, telefono, email)
            flash(f"Cliente '{cliente.nombre_completo}' registrado exitosamente.", "success")
            return redirect(url_for("recepcion.listar_clientes"))
        except DuplicateError:
            flash(f"Ya existe un cliente con el DNI {dni}.", "warning")
            return render_template("recepcion/nuevo_cliente.html"), 409
        except ValidationError as e:
            flash(_mensaje_usuario_error(e), "danger")
            return render_template("recepcion/nuevo_cliente.html"), 400
        except Exception:
            logger.exception("No se pudo registrar el cliente")
            flash("Ocurrió un error al registrar el cliente. Intente nuevamente.", "danger")
            return render_template("recepcion/nuevo_cliente.html"), 503
    return render_template("recepcion/nuevo_cliente.html")


# ──────────────────────────────────────────
# RF 2.2 / 2.3 / 2.4 — Cotizador
# ──────────────────────────────────────────
@recepcion_bp.route("/cotizador", methods=["GET"])
@login_required
@rol_requerido("administrador", "recepcionista")
def cotizador():
    """Pantalla del cotizador de envíos."""
    localidades = _obtener_localidades()
    seguros = _obtener_seguros()
    return render_template(
        "recepcion/cotizador.html",
        localidades=localidades,
        seguros=seguros,
    )


@recepcion_bp.route("/cotizador/calcular", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def calcular_cotizacion():
    """Endpoint AJAX: calcula la tarifa en tiempo real."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Ingresá un objeto JSON válido."), 400
    try:
        resultado = EnvioController().cotizar_envio(
            bultos_data=data.get("bultos"), id_localidad_destino=data.get("id_localidad"),
            valor_declarado=data.get("valor_declarado", 0), id_seguro=data.get("id_seguro"))
        return jsonify(resultado)
    except (ValidationError, CotizacionError) as e:
        return jsonify(error=_mensaje_usuario_error(e)), 400
    except (DatabaseConnectionError, DatabaseQueryError):
        logger.exception("No se pudo cotizar el envío")
        return jsonify(error="No se pudo consultar la cotización. Intentá nuevamente."), 503
    except Exception:
        logger.exception("Error inesperado en cotización")
        return jsonify(error="No se pudo calcular la cotización. Intentá nuevamente."), 500


# ──────────────────────────────────────────
# RF 2.5 — Nuevo Envío completo
# ──────────────────────────────────────────
@recepcion_bp.route("/nuevo-envio", methods=["GET", "POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def nuevo_envio():
    """Formulario completo para registrar un envío."""
    localidades = _obtener_localidades()
    seguros = _obtener_seguros()

    if request.method == "POST":
        try:
            solicitud = SolicitudRecepcion(request.form)
            # Comprobar referencias y cotización antes de crear clientes.
            envio_ctrl = EnvioController()
            envio_ctrl.cotizar_envio(solicitud.bultos, solicitud.localidad, solicitud.declarado, solicitud.seguro)
            cliente_ctrl = ClienteController()
            remitente = cliente_ctrl.obtener_o_crear(**solicitud.clientes["rem"])
            destinatario = cliente_ctrl.obtener_o_crear(**solicitud.clientes["dest"])
            resultado = envio_ctrl.crear_envio(
                id_remitente=remitente.id_cliente, id_destinatario=destinatario.id_cliente,
                id_localidad_destino=solicitud.localidad, direccion_destino=solicitud.direccion,
                bultos_data=solicitud.bultos, modalidad_pago=solicitud.modalidad,
                valor_declarado=solicitud.declarado, id_seguro=solicitud.seguro)

            flash(
                f"✅ Envío registrado. Guía: {resultado['nro_guia']} — Total: ${resultado['cotizacion']['costo_total']:.2f}",
                "success",
            )
            # Redirigir a cobro
            return redirect(url_for(
                "recepcion.cobrar_envio",
                nro_guia=resultado["nro_guia"],
            ))

        except (ValidationError, CotizacionError) as e:
            flash(_mensaje_usuario_error(e, "Los datos del envío no son válidos."), "danger")
            return render_template("recepcion/nuevo_envio.html", localidades=localidades, seguros=seguros), 400
        except DuplicateError:
            flash("Otro registro utilizó esos datos. Revisá el cliente antes de reintentar.", "warning")
            return render_template("recepcion/nuevo_envio.html", localidades=localidades, seguros=seguros), 409
        except Exception:
            logger.exception("No se pudo registrar el envío")
            flash("No se pudo confirmar el registro. Consultá los envíos antes de reintentar.", "danger")
            return render_template("recepcion/nuevo_envio.html", localidades=localidades, seguros=seguros), 503

    return render_template(
        "recepcion/nuevo_envio.html",
        localidades=localidades,
        seguros=seguros,
    )


# ──────────────────────────────────────────
# RF 2.5 — Cobro del envío
# ──────────────────────────────────────────
@recepcion_bp.route("/cobrar/<nro_guia>", methods=["GET", "POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def cobrar_envio(nro_guia: str):
    """Pantalla de cobro de un envío."""
    try:
        envio_ctrl = EnvioController()
        envio = envio_ctrl.obtener_por_guia(nro_guia)
    except EnvioNotFoundError:
        flash(f"No se encontró el envío con guía {nro_guia}.", "danger")
        return redirect(url_for("recepcion.cotizador"))

    envio_dict, detalle = _obtener_detalle_envio(nro_guia)

    qr_base64 = None
    qr_id = None

    conn_check = None
    try:
        db = DatabaseManager.get_instance()
        conn_check = db.get_connection()
        cursor = conn_check.cursor()
        cursor.execute("SELECT 1 FROM pagos WHERE id_envio = %s LIMIT 1", (envio.id_envio,))
        ya_pagado = cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error verificando pago: {e}")
        raise DatabaseQueryError("No se pudo verificar el estado del cobro") from e
    finally:
        if conn_check:
            conn_check.close()

    if ya_pagado:
        if request.method == "POST":
            flash("Este envío ya fue cobrado.", "warning")
        return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))

    if request.method == "POST":
        if envio.estado_actual != 'recibido':
            flash("Este envío ya fue cobrado.", "warning")
            return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))

        tipo_pago = request.form.get("tipo_pago", "efectivo")
        try:
            monto = V.decimal(request.form.get("monto", str(envio.costo_total)), "monto", 0.01)
            monto_entregado = V.decimal(request.form.get("monto_entregado") or "0", "monto_entregado")
        except ValidationError as e:
            flash(_mensaje_usuario_error(e), "warning")
            return render_template("recepcion/cobro.html", envio=envio, detalle=detalle, envio_dict=envio_dict, qr_base64=qr_base64, qr_id=qr_id), 400
        billetera = request.form.get("billetera_virtual", "MercadoPago")
        if monto < float(envio.costo_total):
            flash("El importe cobrado no puede ser inferior al total del envío.", "warning")
            return render_template("recepcion/cobro.html", envio=envio, detalle=detalle, envio_dict=envio_dict, qr_base64=qr_base64, qr_id=qr_id)
        turno_activo = _obtener_turno_activo(session.get("usuario_id"))
        if not turno_activo:
            flash("Debe abrir un turno de caja antes de registrar el cobro.", "warning")
            return render_template("recepcion/cobro.html", envio=envio, detalle=detalle, envio_dict=envio_dict, qr_base64=qr_base64, qr_id=qr_id)

        if tipo_pago == "digital":
            qr_id = request.form.get("id_transaccion_qr") or request.form.get("qr_id")
            if not qr_id:
                qr_id = _generar_id_qr(envio.id_envio, monto)

            try:
                PagoDigital(id_pago=0, id_envio=envio.id_envio, monto=monto, billetera_virtual=billetera).validar_qr(qr_id)
            except ValueError as exc:
                flash(str(exc), "warning")
                return render_template(
                    "recepcion/cobro.html",
                    envio=envio,
                    detalle=detalle,
                    envio_dict=envio_dict,
                    qr_base64=qr_base64,
                    qr_id=qr_id,
                )

        try:
            envio_ctrl.registrar_pago(
                id_envio=envio.id_envio,
                monto=monto,
                tipo_pago=tipo_pago,
                id_turno=turno_activo["id_turno"],
                id_usuario=session["usuario_id"],
                monto_entregado=monto_entregado if tipo_pago == "efectivo" else 0,
                billetera_virtual=billetera if tipo_pago == "digital" else None,
                id_transaccion_qr=(request.form.get("id_transaccion_qr") or request.form.get("qr_id")) if tipo_pago == "digital" else None,
            )
            flash(f"✅ Pago registrado correctamente. Guía: {nro_guia}", "success")
            return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))

        except ValidationError as e:
            flash(_mensaje_usuario_error(e), "warning")
            return render_template("recepcion/cobro.html", envio=envio, detalle=detalle, envio_dict=envio_dict, qr_base64=qr_base64, qr_id=qr_id), 400
        except Exception as e:
            logger.exception("No se pudo registrar el pago")
            flash("Ocurrió un error al procesar el pago. Intente nuevamente.", "danger")

    # Generar QR estático con datos del cobro
    qr_id = _generar_id_qr(envio.id_envio, envio.costo_total)
    qr_base64 = _generar_qr_pago(nro_guia, envio.costo_total)

    return render_template(
        "recepcion/cobro.html",
        envio=envio,
        detalle=detalle,
        envio_dict=envio_dict,
        qr_base64=qr_base64,
        qr_id=qr_id,
    )


# ──────────────────────────────────────────
# RF 2.7 — Comprobante Interno (vista previa + PDF)
# ──────────────────────────────────────────
@recepcion_bp.route("/comprobante/<nro_guia>")
@login_required
def comprobante(nro_guia: str):
    """Vista del comprobante interno."""
    try:
        envio, detalle = _obtener_detalle_envio(nro_guia)
    except Exception:
        flash("No se pudo cargar el comprobante.", "danger")
        return redirect(url_for("recepcion.cotizador"))

    return render_template(
        "recepcion/comprobante.html",
        envio=envio,
        detalle=detalle,
        nro_guia=nro_guia,
    )


@recepcion_bp.route("/comprobante/<nro_guia>/pdf")
@login_required
def descargar_pdf(nro_guia: str):
    """Genera y descarga el comprobante en PDF (ReportLab)."""
    from web.utils.pdf_generator import generar_comprobante_pdf
    try:
        envio, detalle = _obtener_detalle_envio(nro_guia)
        pdf_bytes = generar_comprobante_pdf(envio, detalle)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"comprobante_{nro_guia}.pdf",
        )
    except Exception as e:
        flash("No se pudo generar el PDF. Intente nuevamente.", "danger")
        return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))


@recepcion_bp.route("/comprobante/<nro_guia>/documentos")
@login_required
def descargar_documentos_despacho(nro_guia: str):
    """Descarga tres copias del remito y la etiqueta con código Code128."""
    from web.utils.pdf_generator import generar_documentos_despacho_pdf

    try:
        envio, detalle = _obtener_detalle_envio(nro_guia)
        if not envio:
            raise EnvioNotFoundError(nro_guia=nro_guia)
        pdf_bytes = generar_documentos_despacho_pdf(envio, detalle)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"documentos_{nro_guia}.pdf",
        )
    except Exception as e:
        flash("No se pudieron generar los documentos. Intente nuevamente.", "danger")
        return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))


@recepcion_bp.route("/comprobante/<nro_guia>/etiqueta")
@login_required
def descargar_etiqueta(nro_guia: str):
    """Descarga una etiqueta térmica con código de barras Code128."""
    from web.utils.pdf_generator import generar_etiqueta_pdf

    try:
        envio, _ = _obtener_detalle_envio(nro_guia)
        if not envio:
            raise EnvioNotFoundError(nro_guia=nro_guia)
        pdf_bytes = generar_etiqueta_pdf(envio)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"etiqueta_{nro_guia}.pdf",
        )
    except Exception as e:
        flash("No se pudo generar la etiqueta. Intente nuevamente.", "danger")
        return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))


# ──────────────────────────────────────────
# RF 2.6 — Caja
# ──────────────────────────────────────────
@recepcion_bp.route("/caja")
@login_required
@rol_requerido("administrador", "recepcionista")
def caja():
    """Panel de caja del turno activo."""
    id_usuario = session.get("usuario_id")
    turno_activo = _obtener_turno_activo(id_usuario)
    return render_template("recepcion/caja.html", turno=turno_activo)


@recepcion_bp.route("/caja/abrir", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def abrir_caja():
    """Abre un nuevo turno de caja."""
    try:
        saldo_inicial = V.decimal(request.form.get("saldo_inicial") or "0", "saldo_inicial")
        ctrl = CajaController()
        turno = ctrl.abrir_turno(
            id_recepcionista=session.get("usuario_id"),
            saldo_inicial=saldo_inicial,
        )
        flash(f"✅ Caja abierta. Turno #{turno.id_turno} iniciado.", "success")
    except (TurnoCajaError, ValidationError) as e:
        flash(e.message, "warning")
    except Exception as e:
        flash("Ocurrió un error al abrir la caja. Intente nuevamente.", "danger")
    return redirect(url_for("recepcion.caja"))


@recepcion_bp.route("/caja/cerrar/<int:id_turno>", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def cerrar_caja(id_turno: int):
    """Cierra el turno de caja activo."""
    try:
        ctrl = CajaController()
        resumen = ctrl.cerrar_turno(id_turno, session["usuario_id"])
        flash(
            f"✅ Caja cerrada. Total ingresos: ${resumen['total_ingresos']:.2f} "
            f"(Efectivo: ${resumen['ingresos_efectivo']:.2f} | "
            f"Digital: ${resumen['ingresos_digitales']:.2f})",
            "success",
        )
    except (TurnoCajaError, ValidationError) as e:
        flash(e.message, "warning")
    except Exception as e:
        flash("Ocurrió un error al cerrar la caja. Intente nuevamente.", "danger")
    return redirect(url_for("recepcion.caja"))


# ──────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────
def _obtener_localidades() -> list:
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM localidades ORDER BY nombre ASC")
        return cursor.fetchall()
    except Exception as exc:
        raise DatabaseQueryError("No se pudieron consultar las localidades") from exc
    finally:
        if conn:
            conn.close()


def _obtener_seguros() -> list:
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM seguros ORDER BY cobertura_estandar ASC")
        return cursor.fetchall()
    except Exception as exc:
        raise DatabaseQueryError("No se pudieron consultar los seguros") from exc
    finally:
        if conn:
            conn.close()


def _generar_qr_pago(nro_guia: str, monto: float) -> str:
    """Genera un QR con los datos del pago y lo retorna en base64."""
    # Datos del QR: alias de la empresa + referencia del envío
    # En producción real se usa el alias/CVU de MercadoPago de la empresa
    alias_empresa = "FORMOPACK.EXPRESS"
    texto_qr = f"Alias: {alias_empresa}\nMonto: ${monto:.2f}\nRef: {nro_guia}"

    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(texto_qr)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _generar_id_qr(id_envio: int, monto: float) -> str:
    """Genera la referencia local que identifica el cobro digital."""
    pago = PagoDigital(id_pago=0, id_envio=id_envio, monto=monto, billetera_virtual="MercadoPago")
    return pago.generar_qr(monto)


def _obtener_turno_activo(id_usuario: int):
    """Obtiene el turno de caja abierto del usuario."""
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT tc.*,
                COALESCE((SELECT SUM(monto) FROM pagos WHERE id_turno = tc.id_turno AND tipo_pago='efectivo'), 0) AS ef_real,
                COALESCE((SELECT SUM(monto) FROM pagos WHERE id_turno = tc.id_turno AND tipo_pago='digital'), 0) AS dig_real,
                (SELECT COUNT(*) FROM pagos WHERE id_turno = tc.id_turno) AS cant_pagos
            FROM turnos_caja tc
            WHERE tc.id_recepcionista = %s AND tc.estado_caja = 'abierto'
            LIMIT 1
        """, (id_usuario,))
        return cursor.fetchone()
    except Exception as exc:
        raise DatabaseQueryError("No se pudo consultar el turno activo") from exc
    finally:
        if conn:
            conn.close()


def _obtener_detalle_envio(nro_guia: str):
    """Obtiene los detalles completos de un envío para el comprobante."""
    db = DatabaseManager.get_instance()
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                e.*,
                cr.nombre_completo AS remitente, cr.dni AS rem_dni, cr.telefono AS rem_tel,
                cd.nombre_completo AS destinatario, cd.dni AS dest_dni, cd.telefono AS dest_tel,
                l.nombre AS localidad_destino
            FROM envios e
            JOIN clientes cr ON e.id_remitente = cr.id_cliente
            JOIN clientes cd ON e.id_destinatario = cd.id_cliente
            JOIN localidades l ON e.id_localidad_destino = l.id_localidad
            WHERE e.nro_guia = %s
        """, (nro_guia,))
        envio = cursor.fetchone()

        detalle = {}
        if envio:
            cursor.execute("SELECT * FROM bultos WHERE id_envio = %s", (envio["id_envio"],))
            detalle["bultos"] = cursor.fetchall()

            cursor.execute(
                "SELECT * FROM pagos WHERE id_envio = %s ORDER BY fecha DESC LIMIT 1",
                (envio["id_envio"],)
            )
            detalle["pago"] = cursor.fetchone()

            cursor.execute(
                "SELECT * FROM comprobantes_internos WHERE id_envio = %s ORDER BY fecha_emision DESC LIMIT 1",
                (envio["id_envio"],),
            )
            comprobante_row = cursor.fetchone()
            if not comprobante_row:
                try:
                    nro_comprobante = ComprobanteInterno.generar_nro_comprobante(envio["id_envio"], "recepcion")
                    fecha_emision = envio.get("fecha_creacion") or datetime.now()
                    cursor.execute(
                        """INSERT IGNORE INTO comprobantes_internos (id_envio, nro_comprobante, tipo_comprobante, fecha_emision)
                           VALUES (%s, %s, 'recepcion', %s)""",
                        (envio["id_envio"], nro_comprobante, fecha_emision),
                    )
                    conn.commit()
                    cursor.execute(
                        "SELECT * FROM comprobantes_internos WHERE id_envio = %s ORDER BY fecha_emision DESC LIMIT 1",
                        (envio["id_envio"],),
                    )
                    comprobante_row = cursor.fetchone()
                except Exception as err:
                    logger.warning("No se pudo autogenerar comprobante interno para guia %s: %s", nro_guia, err)
            detalle["comprobante"] = comprobante_row

            # Desglose de seguro y flete
            detalle["seguro"] = None
            detalle["costo_seguro"] = 0.0
            costo_total = float(envio.get("costo_total", 0) or 0)
            detalle["subtotal_flete"] = costo_total

            if envio.get("id_seguro"):
                cursor.execute("SELECT * FROM seguros WHERE id_seguro = %s LIMIT 1", (envio["id_seguro"],))
                seg_row = cursor.fetchone()
                if seg_row:
                    detalle["seguro"] = seg_row
                    vd = float(envio.get("valor_declarado", 0) or 0)
                    cobertura = float(seg_row["cobertura_estandar"])
                    pct = float(seg_row["porcentaje_excedente"])
                    if vd > cobertura:
                        detalle["costo_seguro"] = round((vd - cobertura) * (pct / 100.0), 2)
                    else:
                        detalle["costo_seguro"] = 0.0
                    detalle["subtotal_flete"] = round(costo_total - detalle["costo_seguro"], 2)

        return envio, detalle
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
# RF 2.5 — Integración Mercado Pago (Checkout Pro)
# ═══════════════════════════════════════════════════════════

@recepcion_bp.route('/mp/iniciar/<nro_guia>', methods=['POST'])
@login_required
@rol_requerido('administrador', 'recepcionista')
def mp_iniciar_pago(nro_guia: str):
    """Genera una preferencia de pago en Mercado Pago y redirige al Checkout Pro."""
    if not MercadoPagoConfig.esta_configurado():
        flash('Mercado Pago no está configurado. Completá las credenciales en el .env.', 'warning')
        return redirect(url_for('recepcion.cobrar_envio', nro_guia=nro_guia))

    try:
        envio, _ = _obtener_detalle_envio(nro_guia)
        if not envio:
            flash('No se encontró el envío.', 'danger')
            return redirect(url_for('admin.dashboard'))

        mp = MercadoPagoService()
        preferencia = mp.crear_preferencia(
            nro_guia=nro_guia,
            descripcion=f"Envío FormoPack — Guía {nro_guia}",
            monto=float(envio['costo_total']),
        )

        # Usar sandbox en desarrollo, init_point en producción
        url_checkout = preferencia['sandbox_init_point'] if MercadoPagoConfig.ACCESS_TOKEN.startswith('TEST') \
            else preferencia['init_point']

        logger.info("Mostrando QR de Checkout Pro MP para guía %s — Preferencia %s", nro_guia, preferencia['id'])
        return render_template("recepcion/cobro_mp_qr.html", url_checkout=url_checkout, envio=envio)

    except EnvironmentError as e:
        flash(str(e), 'warning')
    except RuntimeError as e:
        logger.error("Error MP al iniciar pago para %s: %s", nro_guia, e)
        flash('No se pudo conectar con Mercado Pago. Intentá con otro método de pago.', 'danger')
    except Exception as e:
        logger.error("Error inesperado MP para %s: %s", nro_guia, e)
        flash('Ocurrió un error inesperado con Mercado Pago.', 'danger')

    return redirect(url_for('recepcion.cobrar_envio', nro_guia=nro_guia))


@recepcion_bp.route('/mp/verificar/<nro_guia>')
@login_required
@rol_requerido('administrador', 'recepcionista')
def mp_verificar_pago(nro_guia: str):
    """RF 6.3: Endpoint de polling para verificación en vivo de pago MP.

    El frontend llama a este endpoint cada 3 segundos desde la pantalla QR.
    Devuelve JSON indicando si el pago fue aprobado.
    """
    from flask import jsonify as FlaskJson
    conn = None
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_pago, id_transaccion_ext FROM pagos p JOIN envios e ON e.id_envio = p.id_envio WHERE e.nro_guia = %s LIMIT 1",
            (nro_guia,)
        )
        pago_bd = cursor.fetchone()
        cursor.close()
        conn.close()
        conn = None

        if pago_bd:
            # Ya está registrado en la BD (cobro confirmado)
            return FlaskJson({"aprobado": True, "metodo": "bd", "payment_id": pago_bd.get("id_transaccion_ext", "")})

        # No está en BD, consultamos a la API de MP si MP está configurado
        if not MercadoPagoConfig.esta_configurado():
            return FlaskJson({"aprobado": False, "metodo": "sin_mp"})

        mp = MercadoPagoService()
        sdk = mp._sdk
        filtros = {
            "external_reference": nro_guia,
            "sort": "date_created",
            "criteria": "desc",
        }
        resultado = sdk.payment().search(filtros)
        response = resultado.get("response", {})
        pagos = response.get("results", [])

        for p in pagos:
            if str(p.get("status", "")) == "approved":
                payment_id = str(p.get("id", ""))
                monto = float(p.get("transaction_amount", 0))
                # Registrar automáticamente
                _registrar_pago_mp(nro_guia=nro_guia, payment_id=payment_id, monto=monto)
                return FlaskJson({"aprobado": True, "metodo": "api_mp", "payment_id": payment_id})

        return FlaskJson({"aprobado": False, "metodo": "api_mp"})

    except Exception as e:
        logger.error("Error en mp_verificar_pago para %s: %s", nro_guia, e)
        return FlaskJson({"aprobado": False, "metodo": "error", "error": "Error interno"}), 500
    finally:
        if conn:
            conn.close()


@recepcion_bp.route('/mp/success')
def mp_success():
    """Mercado Pago redirige aquí cuando el pago fue APROBADO."""
    payment_id = request.args.get('payment_id', '')
    external_reference = request.args.get('external_reference', '')   # nro_guia
    status = request.args.get('status', '')

    if status == 'approved' and payment_id and external_reference:
        try:
            mp = MercadoPagoService()
            pago = mp.obtener_pago(payment_id)

            if pago and pago['status'] == 'approved':
                # Registrar el pago en la base de datos
                pago_registrado = _registrar_pago_mp(
                    nro_guia=external_reference,
                    payment_id=payment_id,
                    monto=pago['monto'],
                )
                if not pago_registrado:
                    flash('Mercado Pago aprobó el cobro, pero no se pudo conciliar con el envío. Contactá a administración.', 'warning')
                    return redirect(url_for('recepcion.cobrar_envio', nro_guia=external_reference))
                flash(f'Pago aprobado correctamente por Mercado Pago. Referencia: {payment_id}', 'success')
                return redirect(url_for('recepcion.comprobante', nro_guia=external_reference))
        except Exception as e:
            logger.error("Error al procesar MP success para payment_id %s: %s", payment_id, e)

    flash('El pago fue procesado. Verificá el estado en el sistema.', 'info')
    return redirect(url_for('admin.dashboard'))


@recepcion_bp.route('/mp/failure')
@recepcion_bp.route('/mp/pending')
def mp_failure_pending():
    """Mercado Pago redirige aquí cuando el pago fue RECHAZADO o está PENDIENTE."""
    external_reference = request.args.get('external_reference', '')
    status = request.args.get('status', 'unknown')
    logger.warning("Pago MP no completado — guía %s, status: %s", external_reference, status)
    flash('El pago no fue completado o está pendiente de acreditación. Podés reintentar o usar otro método.', 'warning')
    if external_reference:
        return redirect(url_for('recepcion.cobrar_envio', nro_guia=external_reference))
    return redirect(url_for('admin.dashboard'))


@recepcion_bp.route('/mp/webhook', methods=['POST'])
def mp_webhook():
    """Webhook que Mercado Pago llama automáticamente cuando cambia el estado de un pago.

    Este endpoint NO requiere login ya que lo llama el servidor de MP.
    La autenticación se hace validando que el payment_id sea real consultando la API.
    """
    from flask import Response as FlaskResponse
    try:
        data = request.json or {}
        tipo = data.get('type', '')
        accion = data.get('action', '')

        if tipo == 'payment' and accion in ('payment.created', 'payment.updated'):
            payment_id = str(data.get('data', {}).get('id', ''))
            if payment_id:
                mp = MercadoPagoService()
                pago = mp.obtener_pago(payment_id)
                if pago and pago['status'] == 'approved':
                    _registrar_pago_mp(
                        nro_guia=pago['external_reference'],
                        payment_id=payment_id,
                        monto=pago['monto'],
                    )
                    logger.info("Webhook MP: pago %s aprobado para guía %s", payment_id, pago['external_reference'])

    except Exception as e:
        logger.error("Error procesando webhook MP: %s", e)

    # Siempre devolver 200 para que MP no reintente
    return FlaskResponse(status=200)


def _registrar_pago_mp(nro_guia: str, payment_id: str, monto: float) -> bool:
    """Helper interno: registra el pago de MP en la tabla pagos de la BD.

    Evita duplicados verificando si ya existe un pago con el mismo payment_id.
    """
    db = DatabaseManager.get_instance()
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Obtener el envío
        cursor.execute(
            "SELECT id_envio, costo_total FROM envios WHERE nro_guia = %s FOR UPDATE",
            (nro_guia,),
        )
        envio = cursor.fetchone()
        if not envio:
            logger.warning("Webhook MP: no se encontró envío con guía %s", nro_guia)
            return False

        if round(float(monto), 2) != round(float(envio["costo_total"]), 2):
            logger.error("Webhook MP: importe no coincide con el envío %s", nro_guia)
            return False

        # Serializar cobros por envío y hacer idempotentes los reintentos del webhook.
        cursor.execute(
            "SELECT id_pago, id_transaccion_ext FROM pagos WHERE id_envio = %s LIMIT 1",
            (envio["id_envio"],),
        )
        pago_existente = cursor.fetchone()
        if pago_existente:
            if pago_existente.get("id_transaccion_ext") == payment_id:
                logger.info("Pago MP %s ya estaba registrado. Se omite duplicado.", payment_id)
                conn.rollback()
                return True
            else:
                logger.warning("El envío %s ya tiene otro pago registrado; se omite MP %s", nro_guia, payment_id)
                conn.rollback()
                return False

        # Registrar el pago
        id_turno = None  # Los pagos MP pueden llegar fuera de turno de caja
        cursor.execute("""
            INSERT INTO pagos (id_envio, id_turno, monto, tipo_pago, id_transaccion_ext, fecha)
            VALUES (%s, %s, %s, 'digital', %s, NOW())
        """, (envio['id_envio'], id_turno, monto, payment_id))

        cursor.execute(
            """SELECT id_comprobante FROM comprobantes_internos
               WHERE id_envio = %s AND tipo_comprobante = 'recepcion' LIMIT 1""",
            (envio["id_envio"],),
        )
        if not cursor.fetchone():
            nro_comprobante = ComprobanteInterno.generar_nro_comprobante(envio["id_envio"], "recepcion")
            cursor.execute(
                """INSERT INTO comprobantes_internos (id_envio, nro_comprobante, tipo_comprobante)
                   VALUES (%s, %s, 'recepcion')""",
                (envio["id_envio"], nro_comprobante),
            )

        conn.commit()
        logger.info("Pago MP %s registrado para guía %s — $%.2f", payment_id, nro_guia, monto)
        return True

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Error al registrar pago MP en BD para guía %s: %s", nro_guia, e)
        return False
    finally:
        if conn:
            conn.close()

