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
from app.services.referencia_pago import ReferenciaPagoMP
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
        orden_referencia = ReferenciaPagoMP.leer(self.guia)
        if orden_referencia is not None:
            if self.orden is not None and self.orden != orden_referencia:
                raise PagoExternoError("La referencia y los datos de la orden no coinciden.")
            self.orden = orden_referencia
        self.preferencia_verificada = None

    def verificar_orden_comercial(self, proveedor):
        """La API puede omitir metadata: comprobar pago → orden → preferencia."""
        referencia = self.datos.get("order")
        if (not isinstance(referencia, dict) or referencia.get("type") != "mercadopago"
            or not re.fullmatch(r"[0-9]{1,30}", str(referencia.get("id")))):
            raise PagoExternoError("El pago no incluye una orden comercial verificable.")
        orden = proveedor.obtener_orden_comercial(str(referencia["id"]))
        if (not isinstance(orden, dict) or str(orden.get("id")) != str(referencia["id"])
            or orden.get("external_reference") != self.guia
            or not isinstance(orden.get("preference_id"), str)
            or not 1 <= len(orden["preference_id"]) <= 100
            or not isinstance(orden.get("payments"), list)
            or not any(isinstance(p, dict) and str(p.get("id")) == self.id
                       and p.get("status") == "approved" for p in orden["payments"])):
            raise PagoExternoError("La orden comercial no coincide con el pago. Requiere revisión.")
        self.preferencia_verificada = orden["preference_id"]

    def validar(self, orden, guia, revision_legacy=False):
        d = self.datos
        vinculo_valido = (self.orden == orden["id_orden"] if self.orden is not None
                          else self.preferencia_verificada is not None
                          and self.preferencia_verificada == orden["preference_id"])
        if revision_legacy:
            # Solo lo habilita la operación administrativa auditada, nunca el webhook.
            vinculo_valido = self.orden is None and self.guia == guia
        try:
            monto = V.decimal(d.get("transaction_amount"), "importe externo", 0.01)
            devuelto = V.decimal(d.get("transaction_amount_refunded", 0), "reembolso")
        except ValidationError as exc:
            raise PagoExternoError("El importe del pago no es válido.") from exc
        if (not self.aprobado or devuelto != 0
            or self.guia not in {guia, ReferenciaPagoMP.crear(orden["id_orden"])}
            or not vinculo_valido
            or d.get("currency_id") != "ARS"
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
        if pago.orden is None:
            # Consultar al proveedor antes de tomar bloqueos SQL.
            pago.verificar_orden_comercial(self.proveedor)
        elif not isinstance(pago.orden, str) or not re.fullmatch(r"[0-9a-f]{32}", pago.orden):
            raise PagoExternoError("El pago no corresponde a una orden de esta versión del sistema.")
        with self._transaccion() as cur:
            if pago.orden is not None:
                cur.execute("SELECT * FROM ordenes_pago_mp WHERE id_orden=%s", (pago.orden,))
            else:
                cur.execute("SELECT * FROM ordenes_pago_mp WHERE preference_id=%s", (pago.preferencia_verificada,))
            ordenes = cur.fetchall()
            if len(ordenes) != 1:
                raise PagoExternoError("No se encontró la orden local del pago.")
            orden = ordenes[0]
            return self._registrar(cur, pago, orden, guia_esperada)

    @staticmethod
    def _registrar(cur, pago, orden, guia_esperada=None, revision_legacy=False):
        cur.execute("SELECT nro_guia,costo_total FROM envios WHERE id_envio=%s FOR UPDATE", (orden["id_envio"],))
        envio = cur.fetchone()
        if not envio or (guia_esperada is not None and envio["nro_guia"] != guia_esperada):
            raise PagoExternoError("El pago pertenece a otro envío.")
        monto = pago.validar(orden, envio["nro_guia"], revision_legacy)
        if monto != float(envio["costo_total"]):
            raise PagoExternoError("El total del envío cambió. El cobro requiere revisión.")
        cur.execute("SELECT id_pago,id_transaccion_ext FROM pagos WHERE id_envio=%s FOR UPDATE", (orden["id_envio"],))
        existentes = cur.fetchall()
        if existentes:
            if len(existentes) == 1 and existentes[0]["id_transaccion_ext"] == pago.id:
                return {"aprobado": True, "estado": "confirmado", "payment_id": pago.id}
            raise PagoExternoError("El envío ya tiene otro cobro. Requiere revisión de administración.")
        cur.execute("SELECT estado_caja FROM turnos_caja WHERE id_turno=%s FOR UPDATE", (orden["id_turno"],))
        turno = cur.fetchone()
        # Si la caja original ya cerró, no alterar su arqueo histórico.
        id_turno = orden["id_turno"] if turno and turno["estado_caja"] == "abierto" else None
        cur.execute("""INSERT INTO pagos (id_envio,id_turno,monto,tipo_pago,id_transaccion_ext,billetera_virtual)
            VALUES (%s,%s,%s,'digital',%s,'MercadoPago')""", (orden["id_envio"], id_turno, monto, pago.id))
        cur.execute("UPDATE envios SET modalidad_pago='digital' WHERE id_envio=%s", (orden["id_envio"],))
        return {"aprobado": True, "estado": "confirmado", "payment_id": pago.id}

    def verificar(self, guia):
        with self._transaccion() as cur:
            cur.execute("""SELECT p.id_transaccion_ext FROM pagos p JOIN envios e ON e.id_envio=p.id_envio
                WHERE e.nro_guia=%s AND p.id_transaccion_ext IS NOT NULL""", (guia,))
            pagos = cur.fetchall()
        if pagos:
            return {"aprobado": True, "estado": "confirmado", "payment_id": pagos[0]["id_transaccion_ext"]}
        with self._transaccion() as cur:
            cur.execute("""SELECT o.id_orden FROM ordenes_pago_mp o JOIN envios e ON e.id_envio=o.id_envio
                WHERE e.nro_guia=%s""", (guia,))
            orden = cur.fetchone()
        referencias = [ReferenciaPagoMP.crear(orden["id_orden"]), guia] if orden else [guia]
        for referencia in referencias:
            for payment_id in self.proveedor.buscar_pagos(referencia):
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

    @staticmethod
    def _orden_para_revision(cur, guia, id_administrador):
        cur.execute("SELECT activo,tipo_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (id_administrador,))
        actor = cur.fetchone()
        if not actor or not actor["activo"] or actor["tipo_usuario"] != "administrador":
            raise PagoExternoError("La revisión de pagos requiere un administrador activo.", 403)
        cur.execute("""SELECT o.* FROM ordenes_pago_mp o JOIN envios e ON e.id_envio=o.id_envio
            WHERE e.nro_guia=%s""", (guia,))
        orden = cur.fetchone()
        if not orden or not orden["preference_id"]:
            raise PagoExternoError("No se encontró una preferencia local para revisar.")
        return orden

    def _preparar_revision_legacy(self, payment_id, guia, id_administrador):
        self._configuracion()
        id_administrador = V.entero(id_administrador, "administrador")
        if not isinstance(payment_id, str) or not re.fullmatch(r"[0-9]{1,30}", payment_id):
            raise PagoExternoError("El identificador de pago no es válido.", 400)
        with self._transaccion() as cur:
            orden = self._orden_para_revision(cur, guia, id_administrador)
        pago = PagoVerificadoMP(self.proveedor.obtener_pago(payment_id), payment_id)
        # Este procedimiento excepcional solo cubre referencias antiguas de guía.
        if pago.orden is not None or pago.guia != guia or not pago.aprobado:
            raise PagoExternoError("El pago no corresponde a una revisión de referencia antigua.")
        pago.verificar_orden_comercial(self.proveedor)
        original = self.proveedor.obtener_preferencia(orden["preference_id"])
        metadata = original.get("metadata") if isinstance(original, dict) else None
        if (not isinstance(original, dict) or original.get("id") != orden["preference_id"]
            or original.get("external_reference") != guia
            or str(original.get("collector_id")) != orden["collector_id"]
            or not isinstance(metadata, dict) or metadata.get("formopack_orden") != orden["id_orden"]):
            raise PagoExternoError("No se pudo verificar la preferencia original de FormoPack.")
        pago.validar(orden, guia, revision_legacy=True)
        return pago, orden

    def previsualizar_revision_legacy(self, payment_id, guia, id_administrador):
        """Lectura para que administración revise los dos enlaces antes de conciliar."""
        pago, orden = self._preparar_revision_legacy(payment_id, guia, id_administrador)
        return {"guia": guia, "payment_id": pago.id, "monto": float(orden["monto"]),
                "preferencia_original": orden["preference_id"],
                "preferencia_cobro": pago.preferencia_verificada}

    def conciliar_revision_legacy(self, payment_id, guia, id_administrador, motivo):
        """Excepción administrativa explícita, auditada en la misma transacción."""
        motivo = V.texto(motivo, "motivo de revisión", 20, 500)
        pago, revisada = self._preparar_revision_legacy(payment_id, guia, id_administrador)
        with self._transaccion() as cur:
            orden = self._orden_para_revision(cur, guia, id_administrador)
            if orden["id_orden"] != revisada["id_orden"] or orden["preference_id"] != revisada["preference_id"]:
                raise PagoExternoError("La orden cambió durante la revisión. Volvé a consultarla.")
            resultado = self._registrar(cur, pago, orden, guia, revision_legacy=True)
            cur.execute("SELECT id_pago FROM pagos WHERE id_transaccion_ext=%s", (pago.id,))
            id_pago = cur.fetchone()["id_pago"]
            cur.execute("SELECT id_pago FROM revisiones_pago_mp WHERE id_pago=%s", (id_pago,))
            if not cur.fetchone():
                cur.execute("""INSERT INTO revisiones_pago_mp
                    (id_pago,id_orden,id_administrador,preferencia_original,preferencia_cobro,motivo)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (id_pago, orden["id_orden"], id_administrador,
                     orden["preference_id"], pago.preferencia_verificada, motivo))
            return resultado
