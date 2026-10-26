"""Órdenes locales y conciliación idempotente de Checkout Pro (RF 2.5/6.3)."""

import logging
import re
import uuid
import io
import base64
import qrcode
from contextlib import contextmanager
from urllib.parse import urlparse

from app.core.database import DatabaseManager
from app.services.mercadopago_service import MercadoPagoService
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import PagoExternoError, ValidationError
from config.settings import MercadoPagoConfig

logger = logging.getLogger(__name__)


class PagoVerificadoMP:
    def __init__(self, datos, payment_id):
        if not isinstance(datos, dict) or str(datos.get("id")) != payment_id:
            raise PagoExternoError("No se pudo identificar el pago.")
        self.datos = datos
        self.id = payment_id
        self.aprobado = datos.get("status") == "approved"
        self.guia = datos.get("external_reference")
        metadata = datos.get("metadata")
        self.orden = metadata.get("formopack_orden") if isinstance(metadata, dict) else None

    def validar(self, orden, guia):
        d = self.datos
        try:
            monto = V.decimal(d.get("transaction_amount"), "importe externo", 0.01)
            devuelto = V.decimal(d.get("transaction_amount_refunded", 0), "reembolso")
        except ValidationError as exc:
            raise PagoExternoError("El importe del pago no es válido.") from exc
        if (not self.aprobado or devuelto != 0 or self.guia != guia
            or self.orden != orden["id_orden"] or d.get("currency_id") != "ARS"
            or str(d.get("collector_id")) != orden["collector_id"]
            or orden["collector_id"] != str(MercadoPagoConfig.COLLECTOR_ID)
            or type(d.get("live_mode")) is not bool
            or d["live_mode"] != (not MercadoPagoConfig.TEST_MODE)
            or monto != float(orden["monto"])):
            raise PagoExternoError("El pago no coincide con la orden. Requiere revisión de administración.")
        return monto


class ConciliacionMP:
    def __init__(self, db_manager=None, proveedor=None):
        self._db = db_manager or DatabaseManager.get_instance()
        self._proveedor = proveedor

    @property
    def proveedor(self):
        if self._proveedor is None:
            self._proveedor = MercadoPagoService()
        return self._proveedor

    @contextmanager
    def _transaccion(self):
        conn, cur = None, None
        try:
            conn = self._db.get_connection()
            cur = conn.cursor(dictionary=True)
            yield cur
            conn.commit()
        except (PagoExternoError, ValidationError):
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            if getattr(exc, "errno", None) == 1062:
                raise PagoExternoError("El pago ya está asociado a otra operación.") from exc
            logger.error("No se pudo guardar la conciliación de pago", exc_info=True)
            raise PagoExternoError("No se pudo confirmar el pago en el sistema. Reintentá la consulta.", 503, "PAYMENT_UNAVAILABLE") from exc
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    @staticmethod
    def _configuracion():
        if not re.fullmatch(r"[0-9]{1,30}", str(MercadoPagoConfig.COLLECTOR_ID)):
            raise PagoExternoError("La cuenta receptora de Mercado Pago no está configurada.", 503, "PAYMENT_UNAVAILABLE")

    def iniciar(self, guia, id_usuario):
        self._configuracion()
        proveedor = self.proveedor
        id_usuario = V.entero(id_usuario, "usuario")
        id_orden = uuid.uuid4().hex
        with self._transaccion() as cur:
            cur.execute("SELECT activo,tipo_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (id_usuario,))
            usuario = cur.fetchone()
            if not usuario or not usuario["activo"] or usuario["tipo_usuario"] not in {"administrador", "recepcionista"}:
                raise PagoExternoError("La cuenta no puede iniciar cobros.", 403)
            cur.execute("SELECT id_envio,costo_total,nro_guia FROM envios WHERE nro_guia=%s FOR UPDATE", (guia,))
            envio = cur.fetchone()
            if not envio:
                raise PagoExternoError("No se encontró el envío.", 404)
            cur.execute("SELECT id_pago FROM pagos WHERE id_envio=%s", (envio["id_envio"],))
            if cur.fetchall():
                raise PagoExternoError("El envío ya tiene un cobro registrado.")
            cur.execute("SELECT id_turno FROM turnos_caja WHERE id_recepcionista=%s AND estado_caja='abierto' FOR UPDATE", (id_usuario,))
            turnos = cur.fetchall()
            if len(turnos) != 1:
                raise PagoExternoError("Abrí un único turno de caja antes de iniciar el pago.")
            monto = V.decimal(envio["costo_total"], "total", 0.01)
            cur.execute("""SELECT *,TIMESTAMPDIFF(SECOND,fecha_creacion,NOW()) AS segundos FROM ordenes_pago_mp
                WHERE id_envio=%s FOR UPDATE""", (envio["id_envio"],))
            existente = cur.fetchone()
            if existente:
                if float(existente["monto"]) != monto or existente["collector_id"] != str(MercadoPagoConfig.COLLECTOR_ID):
                    raise PagoExternoError("La orden existente requiere revisión antes de generar otro cobro.")
                if existente["preference_id"] and existente["checkout_url"]:
                    return self._presentar(existente["checkout_url"], envio)
                if existente["segundos"] < 30:
                    raise PagoExternoError("Se está preparando el enlace. Aguardá unos segundos antes de reintentar.")
                id_orden = existente["id_orden"]
                cur.execute("UPDATE ordenes_pago_mp SET fecha_creacion=NOW() WHERE id_orden=%s", (id_orden,))
            else:
                cur.execute("""INSERT INTO ordenes_pago_mp (id_orden,id_envio,id_turno,id_usuario,monto,collector_id)
                    VALUES (%s,%s,%s,%s,%s,%s)""", (id_orden, envio["id_envio"], turnos[0]["id_turno"], id_usuario, monto, str(MercadoPagoConfig.COLLECTOR_ID)))
        # La llamada externa no retiene bloqueos de caja o envío.
        preferencia = proveedor.crear_preferencia(guia, f"Servicio de envío {guia}", monto, id_orden)
        url = preferencia.get("sandbox_init_point" if MercadoPagoConfig.TEST_MODE else "init_point", "")
        parsed = urlparse(url)
        if len(url) > 500 or parsed.scheme != "https" or parsed.hostname not in {"www.mercadopago.com.ar", "sandbox.mercadopago.com.ar", "www.mercadopago.com", "sandbox.mercadopago.com"}:
            raise PagoExternoError("No se pudo abrir el enlace de pago.", 503, "PAYMENT_UNAVAILABLE")
        pref_id = V.texto(preferencia.get("id"), "preferencia", 1, 100)
        with self._transaccion() as cur:
            cur.execute("UPDATE ordenes_pago_mp SET preference_id=%s,checkout_url=%s WHERE id_orden=%s", (pref_id, url, id_orden))
        return self._presentar(url, envio)

    @staticmethod
    def _presentar(url, envio):
        imagen = qrcode.make(url)
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG")
        return {"url_checkout": url, "envio": envio, "qr_checkout": base64.b64encode(buffer.getvalue()).decode("ascii")}

    def confirmar(self, payment_id, guia_esperada=None):
        self._configuracion()
        if not isinstance(payment_id, str) or not re.fullmatch(r"[0-9]{1,30}", payment_id):
            raise PagoExternoError("El identificador de pago no es válido.", 400)
        pago = PagoVerificadoMP(self.proveedor.obtener_pago(payment_id), payment_id)
        if not pago.aprobado:
            return {"aprobado": False, "estado": "pendiente"}
        if not isinstance(pago.orden, str) or not re.fullmatch(r"[0-9a-f]{32}", pago.orden):
            raise PagoExternoError("El pago no corresponde a una orden de esta versión del sistema.")
        with self._transaccion() as cur:
            cur.execute("SELECT * FROM ordenes_pago_mp WHERE id_orden=%s", (pago.orden,))
            orden = cur.fetchone()
            if not orden:
                raise PagoExternoError("No se encontró la orden local del pago.")
            cur.execute("SELECT nro_guia,costo_total FROM envios WHERE id_envio=%s FOR UPDATE", (orden["id_envio"],))
            envio = cur.fetchone()
            if not envio or (guia_esperada is not None and envio["nro_guia"] != guia_esperada):
                raise PagoExternoError("El pago pertenece a otro envío.")
            monto = pago.validar(orden, envio["nro_guia"])
            if monto != float(envio["costo_total"]):
                raise PagoExternoError("El total del envío cambió. El cobro requiere revisión.")
            cur.execute("SELECT id_pago,id_transaccion_ext FROM pagos WHERE id_envio=%s FOR UPDATE", (orden["id_envio"],))
            existentes = cur.fetchall()
            if existentes:
                if len(existentes) == 1 and existentes[0]["id_transaccion_ext"] == payment_id:
                    return {"aprobado": True, "estado": "confirmado", "payment_id": payment_id}
                raise PagoExternoError("El envío ya tiene otro cobro. Requiere revisión de administración.")
            cur.execute("SELECT estado_caja FROM turnos_caja WHERE id_turno=%s FOR UPDATE", (orden["id_turno"],))
            turno = cur.fetchone()
            # Si la caja original ya cerró, no alterar su arqueo histórico.
            id_turno = orden["id_turno"] if turno and turno["estado_caja"] == "abierto" else None
            cur.execute("""INSERT INTO pagos (id_envio,id_turno,monto,tipo_pago,id_transaccion_ext,billetera_virtual)
                VALUES (%s,%s,%s,'digital',%s,'MercadoPago')""", (orden["id_envio"], id_turno, monto, payment_id))
            cur.execute("UPDATE envios SET modalidad_pago='digital' WHERE id_envio=%s", (orden["id_envio"],))
            return {"aprobado": True, "estado": "confirmado", "payment_id": payment_id}

    def verificar(self, guia):
        with self._transaccion() as cur:
            cur.execute("""SELECT p.id_transaccion_ext FROM pagos p JOIN envios e ON e.id_envio=p.id_envio
                WHERE e.nro_guia=%s AND p.id_transaccion_ext IS NOT NULL""", (guia,))
            pagos = cur.fetchall()
        if pagos:
            return {"aprobado": True, "estado": "confirmado", "payment_id": pagos[0]["id_transaccion_ext"]}
        for payment_id in self.proveedor.buscar_pagos(guia):
            resultado = self.confirmar(payment_id, guia)
            if resultado["aprobado"]:
                return resultado
        return {"aprobado": False, "estado": "pendiente"}

    def listar_sin_turno(self, id_usuario):
        with self._transaccion() as cur:
            cur.execute("SELECT tipo_usuario,activo FROM usuarios WHERE id_usuario=%s", (id_usuario,))
            actor = cur.fetchone()
            if not actor or not actor["activo"] or actor["tipo_usuario"] != "administrador":
                raise PagoExternoError("Esta consulta corresponde a administración.", 403)
            cur.execute("""SELECT p.monto,p.fecha,p.id_transaccion_ext,e.nro_guia FROM pagos p
                JOIN envios e ON e.id_envio=p.id_envio WHERE p.id_turno IS NULL
                AND p.id_transaccion_ext IS NOT NULL ORDER BY p.fecha DESC,p.id_pago DESC LIMIT 100""")
            return cur.fetchall()
