"""
Rutas de Recepción — Cotizador, Nuevo Envío, Cobro, Caja
Blueprint: recepcion_bp
"""

import io
import logging
import qrcode
import base64
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
    ClienteNotFoundError, EnvioNotFoundError, TurnoCajaError,
)
from app.services.cotizador import Cotizador
from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro

recepcion_bp = Blueprint("recepcion", __name__)
logger = logging.getLogger(__name__)


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
    except Exception as e:
        return jsonify({"encontrado": False, "error": str(e)})


@recepcion_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def nuevo_cliente():
    """Registro de un nuevo cliente."""
    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        nombre = request.form.get("nombre_completo", "").strip()
        telefono = request.form.get("telefono", "").strip()
        try:
            ctrl = ClienteController()
            cliente = ctrl.registrar_cliente(dni, nombre, telefono)
            flash(f"Cliente '{cliente.nombre_completo}' registrado exitosamente.", "success")
            return redirect(url_for("recepcion.listar_clientes"))
        except DuplicateError:
            flash(f"Ya existe un cliente con el DNI {dni}.", "warning")
        except ValidationError as e:
            flash(e.message, "danger")
        except Exception as e:
            flash(f"Error al registrar cliente: {e}", "danger")
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
def calcular_cotizacion():
    """Endpoint AJAX: calcula la tarifa en tiempo real."""
    try:
        data = request.get_json()
        bultos_data = data.get("bultos", [])
        id_localidad = int(data.get("id_localidad", 0))
        valor_declarado = float(data.get("valor_declarado", 0))
        id_seguro = data.get("id_seguro")

        if not bultos_data or not id_localidad:
            return jsonify({"error": "Faltan datos obligatorios."}), 400

        ctrl = EnvioController()
        resultado = ctrl.cotizar_envio(
            bultos_data=bultos_data,
            id_localidad_destino=id_localidad,
            valor_declarado=valor_declarado,
            id_seguro=int(id_seguro) if id_seguro else None,
        )
        return jsonify(resultado)

    except Exception as e:
        logger.error("Error en cotización AJAX: %s", e)
        return jsonify({"error": str(e)}), 500


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
            form = request.form

            # Remitente
            cliente_ctrl = ClienteController()
            remitente = cliente_ctrl.obtener_o_crear(
                dni=form.get("rem_dni", "").strip(),
                nombre_completo=form.get("rem_nombre", "").strip(),
                telefono=form.get("rem_telefono", "").strip(),
            )

            # Destinatario
            destinatario = cliente_ctrl.obtener_o_crear(
                dni=form.get("dest_dni", "").strip(),
                nombre_completo=form.get("dest_nombre", "").strip(),
                telefono=form.get("dest_telefono", "").strip(),
            )

            # Bultos (vienen como listas del form)
            pesos_reales = request.form.getlist("peso_real[]")
            pesos_vol = request.form.getlist("peso_volumetrico[]")
            es_fragil_list = request.form.getlist("es_fragil[]")

            bultos_data = []
            for i in range(len(pesos_reales)):
                bultos_data.append({
                    "peso_real": float(pesos_reales[i] or 0),
                    "peso_volumetrico": float(pesos_vol[i] or 0),
                    "es_fragil": str(i) in es_fragil_list,
                })

            # Crear envío
            envio_ctrl = EnvioController()
            resultado = envio_ctrl.crear_envio(
                id_remitente=remitente.id_cliente,
                id_destinatario=destinatario.id_cliente,
                id_localidad_destino=int(form.get("id_localidad_destino")),
                direccion_destino=form.get("direccion_destino", "").strip(),
                bultos_data=bultos_data,
                modalidad_pago=form.get("modalidad_pago", "efectivo"),
                valor_declarado=float(form.get("valor_declarado", 0) or 0),
                id_seguro=int(form.get("id_seguro")) if form.get("id_seguro") else None,
            )

            flash(
                f"✅ Envío registrado. Guía: {resultado['nro_guia']} — Total: ${resultado['cotizacion']['costo_total']:.2f}",
                "success",
            )
            # Redirigir a cobro
            return redirect(url_for(
                "recepcion.cobrar_envio",
                nro_guia=resultado["nro_guia"],
            ))

        except ValidationError as e:
            flash(e.message, "danger")
        except Exception as e:
            logger.error("Error al crear envío: %s", e)
            flash(f"Error al registrar el envío: {e}", "danger")

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

    qr_base64 = None

    if request.method == "POST":
        tipo_pago = request.form.get("tipo_pago", "efectivo")
        try:
            monto = float(request.form.get("monto", envio.costo_total))
        except (ValueError, TypeError):
            monto = envio.costo_total
        try:
            monto_entregado = float(request.form.get("monto_entregado", 0) or 0)
        except (ValueError, TypeError):
            monto_entregado = 0.0
        billetera = request.form.get("billetera_virtual", "MercadoPago")

        try:
            envio_ctrl.registrar_pago(
                id_envio=envio.id_envio,
                monto=monto,
                tipo_pago=tipo_pago,
                monto_entregado=monto_entregado if tipo_pago == "efectivo" else 0,
                billetera_virtual=billetera if tipo_pago == "digital" else None,
            )
            flash(f"✅ Pago registrado correctamente. Guía: {nro_guia}", "success")
            return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))

        except Exception as e:
            flash(f"Error al registrar pago: {e}", "danger")

    # Generar QR estático con datos del cobro
    qr_base64 = _generar_qr_pago(nro_guia, envio.costo_total)

    return render_template(
        "recepcion/cobro.html",
        envio=envio,
        qr_base64=qr_base64,
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
        flash(f"Error al generar PDF: {e}", "danger")
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
        saldo_inicial = float(request.form.get("saldo_inicial", 0) or 0)
    except (ValueError, TypeError):
        saldo_inicial = 0.0
    try:
        ctrl = CajaController()
        turno = ctrl.abrir_turno(
            id_recepcionista=session.get("usuario_id"),
            saldo_inicial=saldo_inicial,
        )
        flash(f"✅ Caja abierta. Turno #{turno.id_turno} iniciado.", "success")
    except TurnoCajaError as e:
        flash(e.message, "warning")
    except Exception as e:
        flash(f"Error al abrir caja: {e}", "danger")
    return redirect(url_for("recepcion.caja"))


@recepcion_bp.route("/caja/cerrar/<int:id_turno>", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def cerrar_caja(id_turno: int):
    """Cierra el turno de caja activo."""
    try:
        ctrl = CajaController()
        resumen = ctrl.cerrar_turno(id_turno)
        flash(
            f"✅ Caja cerrada. Total ingresos: ${resumen['total_ingresos']:.2f} "
            f"(Efectivo: ${resumen['ingresos_efectivo']:.2f} | "
            f"Digital: ${resumen['ingresos_digitales']:.2f})",
            "success",
        )
    except TurnoCajaError as e:
        flash(e.message, "warning")
    except Exception as e:
        flash(f"Error al cerrar caja: {e}", "danger")
    return redirect(url_for("recepcion.caja"))


# ──────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────
def _obtener_localidades() -> list:
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM localidades ORDER BY nombre ASC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        return []


def _obtener_seguros() -> list:
    try:
        db = DatabaseManager.get_instance()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM seguros ORDER BY cobertura_estandar ASC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        return []


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


def _obtener_turno_activo(id_usuario: int):
    """Obtiene el turno de caja abierto del usuario."""
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
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row
    except Exception:
        return None


def _obtener_detalle_envio(nro_guia: str):
    """Obtiene los detalles completos de un envío para el comprobante."""
    db = DatabaseManager.get_instance()
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)

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

    # Bultos del envío
    detalle = {}
    if envio:
        cursor.execute("SELECT * FROM bultos WHERE id_envio = %s", (envio["id_envio"],))
        detalle["bultos"] = cursor.fetchall()

        # Pago registrado
        cursor.execute(
            "SELECT * FROM pagos WHERE id_envio = %s ORDER BY fecha DESC LIMIT 1",
            (envio["id_envio"],)
        )
        detalle["pago"] = cursor.fetchone()

    cursor.close()
    conn.close()
    return envio, detalle
