"""Adaptador exclusivo del SDK de Checkout Pro mediante Preferences API."""

import logging
import mercadopago
from mercadopago.config import RequestOptions
from config.settings import MercadoPagoConfig
from app.utils.exceptions import PagoExternoError

logger = logging.getLogger(__name__)


class MercadoPagoService:
    def __init__(self):
        if not MercadoPagoConfig.esta_configurado():
            raise PagoExternoError("Mercado Pago no está disponible.", 503, "PAYMENT_UNAVAILABLE")
        self._sdk = mercadopago.SDK(MercadoPagoConfig.ACCESS_TOKEN,
            request_options=RequestOptions(connection_timeout=8.0, max_retries=0))

    def _respuesta(self, operacion):
        try:
            resultado = operacion()
            if resultado.get("status") not in (200, 201) or not isinstance(resultado.get("response"), dict):
                raise ValueError("Respuesta no exitosa")
            return resultado["response"]
        except Exception as exc:
            logger.warning("Mercado Pago no pudo completar una consulta")
            raise PagoExternoError("No se pudo consultar Mercado Pago. Intentá nuevamente.", 503, "PAYMENT_UNAVAILABLE") from exc

    def crear_preferencia(self, nro_guia, descripcion, monto, id_orden):
        cfg = MercadoPagoConfig
        return self._respuesta(lambda: self._sdk.preference().create({
            "items": [{"title": f"FormoPack — {nro_guia}", "description": descripcion,
                       "quantity": 1, "unit_price": monto, "currency_id": "ARS"}],
            "payment_methods": {"excluded_payment_types": [{"id": "credit_card"}, {"id": "debit_card"}, {"id": "prepaid_card"}]},
            "external_reference": nro_guia,
            "metadata": {"formopack_orden": id_orden},
            "back_urls": {"success": cfg.SUCCESS_URL, "failure": cfg.FAILURE_URL, "pending": cfg.PENDING_URL},
            "notification_url": cfg.WEBHOOK_URL,
            "statement_descriptor": "FORMOPACK EXPRESS"}))

    def obtener_pago(self, payment_id):
        return self._respuesta(lambda: self._sdk.payment().get(payment_id))

    def buscar_pagos(self, nro_guia):
        respuesta = self._respuesta(lambda: self._sdk.payment().search({
            "external_reference": nro_guia, "sort": "date_created", "criteria": "desc", "limit": 30}))
        resultados = respuesta.get("results")
        if not isinstance(resultados, list):
            raise PagoExternoError("No se pudo consultar Mercado Pago.", 503, "PAYMENT_UNAVAILABLE")
        return [str(p["id"]) for p in resultados if isinstance(p, dict) and p.get("id") and p.get("status") == "approved"]
