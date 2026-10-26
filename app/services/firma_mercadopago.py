"""Autenticación de notificaciones Checkout Pro mediante HMAC-SHA256."""

import hashlib
import hmac
import re
import time

from app.utils.exceptions import PagoExternoError


class FirmaMercadoPago:
    def __init__(self, secreto, reloj=time.time):
        self._secreto, self._reloj = secreto, reloj

    def validar(self, firma, request_id, data_id):
        if not self._secreto:
            raise PagoExternoError("El receptor de pagos no está disponible.", 503, "PAYMENT_UNAVAILABLE")
        try:
            if not isinstance(firma, str) or len(firma) > 300:
                raise ValueError
            partes = [p.strip().split("=", 1) for p in firma.split(",")]
            if len(partes) != 2 or len(dict(partes)) != 2:
                raise ValueError
            campos = dict(partes)
            ts, digest = campos["ts"], campos["v1"]
            if not re.fullmatch(r"[0-9]{10,13}", ts) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise ValueError
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", request_id):
                raise ValueError
            if not isinstance(data_id, str) or not re.fullmatch(r"[0-9]{1,30}", data_id):
                raise ValueError
            instante = int(ts) / (1000 if len(ts) == 13 else 1)
            if abs(self._reloj() - instante) > 300:
                raise ValueError
            manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
            esperado = hmac.new(self._secreto.encode(), manifest.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(esperado, digest.lower()):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise PagoExternoError("La notificación no es válida.", 401, "INVALID_SIGNATURE") from None
