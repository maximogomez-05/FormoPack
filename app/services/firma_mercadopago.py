"""Autenticación de notificaciones Checkout Pro mediante HMAC-SHA256."""

import hashlib
import hmac
import logging
import re
import time

from app.utils.exceptions import PagoExternoError


logger = logging.getLogger(__name__)


class FirmaMercadoPago:
    def __init__(self, secreto, reloj=time.time):
        self._secreto, self._reloj = secreto, reloj

    def validar(self, firma, request_id, data_id):
        if not self._secreto:
            raise PagoExternoError("El receptor de pagos no está disponible.", 503, "PAYMENT_UNAVAILABLE")
        motivo = "encabezado ausente o demasiado largo"
        try:
            if not isinstance(firma, str) or len(firma) > 300:
                raise ValueError
            motivo = "estructura del encabezado de firma"
            partes = [p.strip().split("=", 1) for p in firma.split(",")]
            if len(partes) != 2 or len(dict(partes)) != 2:
                raise ValueError
            campos = dict(partes)
            motivo = "campos ts o v1 ausentes o inválidos"
            ts, digest = campos["ts"], campos["v1"]
            if not re.fullmatch(r"[0-9]{10,13}", ts) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise ValueError
            motivo = "x-request-id ausente o con formato no admitido"
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", request_id):
                raise ValueError
            motivo = "data.id ausente o inválido"
            if not isinstance(data_id, str) or not re.fullmatch(r"[0-9]{1,30}", data_id):
                raise ValueError
            motivo = "timestamp fuera de la ventana de cinco minutos"
            instante = int(ts) / (1000 if len(ts) == 13 else 1)
            if abs(self._reloj() - instante) > 300:
                raise ValueError
            motivo = "HMAC distinto al esperado"
            manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
            esperado = hmac.new(self._secreto.encode(), manifest.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(esperado, digest.lower()):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            logger.warning("Webhook MP rechazado: %s", motivo)
            raise PagoExternoError("La notificación no es válida.", 401, "INVALID_SIGNATURE") from None
