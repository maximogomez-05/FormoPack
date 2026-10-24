"""Adaptadores Flask del canal de soporte (RF 5.6)."""

import hashlib
import hmac
import secrets

from flask import Blueprint, current_app, render_template, request, jsonify, redirect, url_for, session, flash
from flask_limiter.util import get_remote_address

from app.controllers.soporte_controller import SoporteController
from app.models.chat_soporte import ChatSoporte
from app.utils.exceptions import SoporteError, DatabaseQueryError, DatabaseConnectionError
from web.routes.auth import login_required, rol_requerido
from web.extensions import limiter
from web.security.error_handlers import ManejadorErroresSeguridad

soporte_bp = Blueprint("soporte", __name__)


class IdentidadClienteSoporte:
    CLAVE = "soporte_cliente_token"

    @classmethod
    def token(cls, crear=False):
        token = session.get(cls.CLAVE)
        if not token and crear:
            # El SID ya es aleatorio. Derivarlo evita duplicar chats si dos
            # solicitudes de inicio llegan juntas desde el mismo navegador.
            token = hmac.new(current_app.secret_key.encode("utf-8"),
                             f"soporte:{session.sid}".encode("utf-8"), hashlib.sha256).hexdigest()
            session[cls.CLAVE] = token
        return token

    @classmethod
    def renovar(cls):
        session[cls.CLAVE] = secrets.token_hex(32)
        return session[cls.CLAVE]

    @classmethod
    def clave_limite(cls):
        return cls.token() or get_remote_address()


class PresentacionSoporte:
    @staticmethod
    def datos(campos):
        if request.is_json:
            datos = request.get_json(silent=True)
            if not isinstance(datos, dict):
                raise SoporteError("Revisá los datos de la solicitud.")
        else:
            datos = request.form.to_dict()
        if set(datos) - set(campos) - {"csrf_token"}:
            raise SoporteError("Revisá los datos de la solicitud.")
        return datos

    @staticmethod
    def mensaje(fila):
        return {
            "id_mensaje": fila["id_mensaje"], "remitente_tipo": fila["remitente_tipo"],
            "remitente_nombre": fila["remitente_nombre"], "mensaje": fila["mensaje"],
            "fecha_envio": fila["fecha_envio"].strftime("%H:%M"),
        }

    @classmethod
    def conversacion(cls, chat, mensajes):
        cerrado = not chat or ChatSoporte(chat).cerrado
        return {
            "ok": True, "finalizado": cerrado,
            "estado": chat["estado"] if chat else "cerrado",
            "agente": chat.get("nombre_usuario_atendiendo") if chat else None,
            "mensajes": [cls.mensaje(m) for m in mensajes] if not cerrado else [],
        }


@soporte_bp.errorhandler(SoporteError)
def error_soporte(error):
    if ManejadorErroresSeguridad.espera_json():
        return jsonify(ok=False, code=error.code, error=error.message, finalizado=error.code == "CHAT_CLOSED"), error.status
    return render_template("errors/seguridad.html", mensaje=error.message, estado=error.status,
                           reintentar_url=url_for("soporte.panel")), error.status


@soporte_bp.errorhandler(DatabaseConnectionError)
@soporte_bp.errorhandler(DatabaseQueryError)
def error_persistencia(error):
    return error_soporte(SoporteError("Soporte no está disponible. Intentá nuevamente en unos instantes.", 503, "SERVICE_UNAVAILABLE"))


@soporte_bp.route("/panel")
@login_required
@rol_requerido("administrador", "recepcionista")
def panel():
    ctrl = SoporteController()
    datos = ctrl.listar_chats(session["usuario_id"])
    return render_template("soporte/panel.html", **datos,
                           chat_activo=ctrl.agente_tiene_chat_en_progreso(session["usuario_id"]))


@soporte_bp.route("/chat/<int:id_chat>")
@login_required
@rol_requerido("administrador", "recepcionista")
def ver_chat(id_chat):
    ctrl = SoporteController()
    chat, mensajes = ctrl.consultar_staff(id_chat, session["usuario_id"])
    activo = ctrl.agente_tiene_chat_en_progreso(session["usuario_id"])
    politica = ChatSoporte(chat)
    return render_template(
        "soporte/chat.html", chat=chat, mensajes=mensajes, chat_activo=activo,
        es_mi_chat=chat["id_usuario_atendiendo"] == session["usuario_id"],
        puede_atender=chat["estado"] == "sin_atender" and not activo,
        puede_finalizar=politica.puede_finalizar(session["usuario_id"], session["rol"]),
    )


@soporte_bp.route("/chat/<int:id_chat>/tomar", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def tomar_chat(id_chat):
    SoporteController().tomar_chat(id_chat, session["usuario_id"])
    flash("Conversación asignada. Ya podés responder.", "success")
    return redirect(url_for("soporte.ver_chat", id_chat=id_chat))


@soporte_bp.route("/chat/<int:id_chat>/mensaje", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def enviar_mensaje_staff(id_chat):
    datos = PresentacionSoporte.datos({"mensaje"})
    mensaje = SoporteController().enviar_staff(id_chat, session["usuario_id"], datos.get("mensaje"))
    if ManejadorErroresSeguridad.espera_json():
        return jsonify(ok=True, mensaje=PresentacionSoporte.mensaje(mensaje))
    return redirect(url_for("soporte.ver_chat", id_chat=id_chat))


@soporte_bp.route("/chat/<int:id_chat>/finalizar", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def finalizar_chat_staff(id_chat):
    SoporteController().finalizar_staff(id_chat, session["usuario_id"])
    if request.is_json:
        return jsonify(ok=True, finalizado=True)
    flash("Conversación finalizada. Los mensajes fueron eliminados.", "success")
    return redirect(url_for("soporte.panel"))


@soporte_bp.route("/api/chat/<int:id_chat>/mensajes")
@login_required
@rol_requerido("administrador", "recepcionista")
def api_chat_mensajes_staff(id_chat):
    chat, mensajes = SoporteController().consultar_staff(id_chat, session["usuario_id"])
    return jsonify(PresentacionSoporte.conversacion(chat, mensajes))


@soporte_bp.route("/api/iniciar", methods=["POST"])
@limiter.limit("5 per minute")
def api_cliente_iniciar():
    datos = PresentacionSoporte.datos({"cliente_nombre", "cliente_email", "nro_guia", "mensaje"})
    ctrl = SoporteController()
    argumentos = {"nombre": datos.get("cliente_nombre"), "email": datos.get("cliente_email"),
                  "guia": datos.get("nro_guia"), "mensaje": datos.get("mensaje")}
    try:
        chat = ctrl.iniciar_chat(IdentidadClienteSoporte.token(True), **argumentos)
    except SoporteError as error:
        if error.code != "CHAT_CLOSED":
            raise
        chat = ctrl.iniciar_chat(IdentidadClienteSoporte.renovar(), **argumentos)
    return jsonify(ok=True, id_chat=chat["id_chat"], estado=chat["estado"], agente=chat["nombre_usuario_atendiendo"])


@soporte_bp.route("/api/mensajes")
@limiter.limit("60 per minute", key_func=IdentidadClienteSoporte.clave_limite)
def api_cliente_mensajes():
    if request.args:
        raise SoporteError("Revisá los datos de la solicitud.")
    chat, mensajes = SoporteController().consultar_cliente(IdentidadClienteSoporte.token())
    return jsonify(PresentacionSoporte.conversacion(chat, mensajes))


@soporte_bp.route("/api/enviar", methods=["POST"])
@limiter.limit("30 per minute", key_func=IdentidadClienteSoporte.clave_limite)
def api_cliente_enviar():
    datos = PresentacionSoporte.datos({"mensaje"})
    mensaje = SoporteController().enviar_cliente(IdentidadClienteSoporte.token(), datos.get("mensaje"))
    return jsonify(ok=True, id_mensaje=mensaje["id_mensaje"])


@soporte_bp.route("/api/finalizar", methods=["POST"])
@limiter.limit("10 per minute", key_func=IdentidadClienteSoporte.clave_limite)
def api_cliente_finalizar():
    PresentacionSoporte.datos(set())
    SoporteController().finalizar_cliente(IdentidadClienteSoporte.token())
    return jsonify(ok=True, finalizado=True)
