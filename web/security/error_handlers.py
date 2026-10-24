"""Respuestas HTTP explícitas para errores de seguridad."""

import logging

from flask import jsonify, render_template, request
from flask_wtf.csrf import CSRFError


class ManejadorErroresSeguridad:
    """Evita que un rechazo de seguridad se interprete como un envío exitoso."""

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def registrar(self, app) -> None:
        app.register_error_handler(CSRFError, self.error_csrf)
        app.register_error_handler(429, self.limite_excedido)
        app.register_error_handler(503, self.servicio_no_disponible)

    @staticmethod
    def espera_json() -> bool:
        return (
            request.path.startswith("/soporte/api/")
            or request.is_json
            or request.headers.get("X-Offline-Sync") == "1"
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json"
        )

    def _respuesta(self, mensaje: str, codigo: str, estado: int):
        if self.espera_json():
            return jsonify(ok=False, error=mensaje, code=codigo), estado
        return render_template(
            "errors/seguridad.html", mensaje=mensaje, estado=estado,
            reintentar_url=request.path if (
                estado == 400 and request.url_rule and "GET" in request.url_rule.methods
            ) else None,
        ), estado

    def error_csrf(self, error):
        self._logger.warning("Solicitud rechazada por CSRF: %s", request.path)
        return self._respuesta(
            "El formulario venció o no es válido. Volvé a abrirlo antes de reintentar.",
            "CSRF_ERROR", 400,
        )

    def limite_excedido(self, error):
        return self._respuesta(
            "Demasiados intentos. Aguardá un minuto antes de reintentar.",
            "RATE_LIMIT_EXCEEDED", 429,
        )

    def servicio_no_disponible(self, error):
        return self._respuesta(
            "No pudimos verificar tu acceso. Intentá nuevamente en unos instantes.",
            "SERVICE_UNAVAILABLE", 503,
        )
