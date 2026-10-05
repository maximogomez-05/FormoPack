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
    DatabaseQueryError, ClienteNotFoundError, EnvioNotFoundError,
    TurnoCajaError,
)
from app.services.cotizador import Cotizador
from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from app.models.pago import PagoDigital
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
        return "La base de datos está desactualizada: falta una columna del sistema (por ejemplo, email). Actualizá la estructura de la tabla clientes o ejecutá el script de inicialización."

    return texto or fallback


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
        return jsonify({"encontrado": False, "error": "Error interno"})


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
            return redirect(request.url)
        except ValidationError as e:
            flash(e.message, "danger")
            return redirect(request.url)
        except Exception as e:
            flash("Ocurrió un error al registrar el cliente. Intente nuevamente.", "danger")
            return redirect(request.url)
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
        return jsonify({"error": "Error al calcular cotización"}), 500


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
                email=form.get("rem_email", "").strip() or None,
            )

            # Destinatario
            destinatario = cliente_ctrl.obtener_o_crear(
                dni=form.get("dest_dni", "").strip(),
                nombre_completo=form.get("dest_nombre", "").strip(),
                telefono=form.get("dest_telefono", "").strip(),
                email=form.get("dest_email", "").strip() or None,
            )

            # Bultos (vienen como listas del form)
            pesos_reales = request.form.getlist("peso_real[]")
            pesos_vol = request.form.getlist("peso_volumetrico[]")
            es_fragil_list = request.form.getlist("es_fragil[]")

            bultos_data = []
            for i in range(len(pesos_reales)):
                try:
                    peso_real = float(pesos_reales[i] or 0)
                    peso_vol = float(pesos_vol[i] if i < len(pesos_vol) else 0)
                except (ValueError, TypeError):
                    peso_real = 0.0
                    peso_vol = 0.0
                # es_fragil se detecta por posición relativa, no por value del checkbox
                es_fragil = len(es_fragil_list) > i and es_fragil_list[i] in ('on', '1', 'true', str(i))
                bultos_data.append({
                    "peso_real": peso_real,
                    "peso_volumetrico": peso_vol,
                    "es_fragil": es_fragil,
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
            flash(_mensaje_usuario_error(e, "Los datos del envío no son válidos."), "danger")
            return redirect(request.url)
        except (DuplicateError, DatabaseConnectionError, DatabaseQueryError) as e:
            logger.error("Error al crear envío: %s", e)
            flash(_mensaje_usuario_error(e, "No se pudo registrar el envío."), "danger")
            return redirect(request.url)
        except Exception as e:
            logger.error("Error al crear envío: %s", e)
            flash(_mensaje_usuario_error(e, "No se pudo registrar el envío."), "danger")
            return redirect(request.url)

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
        ya_pagado = False
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
            monto = float(request.form.get("monto", envio.costo_total))
        except (ValueError, TypeError):
            monto = envio.costo_total
        try:
            monto_entregado = float(request.form.get("monto_entregado", 0) or 0)
        except (ValueError, TypeError):
            monto_entregado = 0.0
        billetera = request.form.get("billetera_virtual", "MercadoPago")
        if monto < float(envio.costo_total):
            flash("El importe cobrado no puede ser inferior al total del envío.", "warning")
            return render_template("recepcion/cobro.html", envio=envio, qr_base64=qr_base64, qr_id=qr_id)
        turno_activo = _obtener_turno_activo(session.get("usuario_id"))
        if not turno_activo:
            flash("Debe abrir un turno de caja antes de registrar el cobro.", "warning")
            return render_template("recepcion/cobro.html", envio=envio, qr_base64=qr_base64, qr_id=qr_id)

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
                    qr_base64=qr_base64,
                    qr_id=qr_id,
                )

        try:
            envio_ctrl.registrar_pago(
                id_envio=envio.id_envio,
                monto=monto,
                tipo_pago=tipo_pago,
                id_turno=turno_activo["id_turno"],
                monto_entregado=monto_entregado if tipo_pago == "efectivo" else 0,
                billetera_virtual=billetera if tipo_pago == "digital" else None,
                id_transaccion_qr=(request.form.get("id_transaccion_qr") or request.form.get("qr_id")) if tipo_pago == "digital" else None,
            )
            flash(f"✅ Pago registrado correctamente. Guía: {nro_guia}", "success")
            return redirect(url_for("recepcion.comprobante", nro_guia=nro_guia))

        except Exception as e:
            flash("Ocurrió un error al procesar el pago. Intente nuevamente.", "danger")

    # Generar QR estático con datos del cobro
    qr_id = _generar_id_qr(envio.id_envio, envio.costo_total)
    qr_base64 = _generar_qr_pago(nro_guia, envio.costo_total)

    return render_template(
        "recepcion/cobro.html",
        envio=envio,
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
        flash("Ocurrió un error al abrir la caja. Intente nuevamente.", "danger")
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
    except Exception:
        return []
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
    except Exception:
        return []
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
    except Exception:
        return None
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
            detalle["comprobante"] = cursor.fetchone()

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
            return redirect(url_for('recepcion.dashboard'))

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
                _registrar_pago_mp(
                    nro_guia=external_reference,
                    payment_id=payment_id,
                    monto=pago['monto'],
                )
                flash(f'Pago aprobado correctamente por Mercado Pago. Referencia: {payment_id}', 'success')
                return redirect(url_for('recepcion.comprobante', nro_guia=external_reference))
        except Exception as e:
            logger.error("Error al procesar MP success para payment_id %s: %s", payment_id, e)

    flash('El pago fue procesado. Verificá el estado en el sistema.', 'info')
    return redirect(url_for('recepcion.dashboard'))


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
    return redirect(url_for('recepcion.dashboard'))


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


def _registrar_pago_mp(nro_guia: str, payment_id: str, monto: float) -> None:
    """Helper interno: registra el pago de MP en la tabla pagos de la BD.

    Evita duplicados verificando si ya existe un pago con el mismo payment_id.
    """
    db = DatabaseManager.get_instance()
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Obtener el envío
        cursor.execute("SELECT id_envio FROM envios WHERE nro_guia = %s", (nro_guia,))
        envio = cursor.fetchone()
        if not envio:
            logger.warning("Webhook MP: no se encontró envío con guía %s", nro_guia)
            return

        # Verificar que no se registre dos veces
        cursor.execute(
            "SELECT id_pago FROM pagos WHERE id_transaccion_ext = %s LIMIT 1",
            (payment_id,)
        )
        if cursor.fetchone():
            logger.info("Pago MP %s ya estaba registrado. Se omite duplicado.", payment_id)
            return

        # Registrar el pago
        id_turno = None  # Los pagos MP pueden llegar fuera de turno de caja
        cursor.execute("""
            INSERT INTO pagos (id_envio, id_turno, monto, tipo_pago, id_transaccion_ext, fecha)
            VALUES (%s, %s, %s, 'digital', %s, NOW())
        """, (envio['id_envio'], id_turno, monto, payment_id))

        conn.commit()
        logger.info("Pago MP %s registrado para guía %s — $%.2f", payment_id, nro_guia, monto)

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Error al registrar pago MP en BD para guía %s: %s", nro_guia, e)
    finally:
        if conn:
            conn.close()

