"""Rutas para el sistema de Soporte al Cliente — Chats en vivo.
Blueprint: soporte_bp
Accesible tanto para administradores como para recepcionistas, y API pública para clientes en tracking.
"""

import uuid
import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from web.routes.auth import login_required, rol_requerido
from app.controllers.soporte_controller import SoporteController

soporte_bp = Blueprint("soporte", __name__)
logger = logging.getLogger(__name__)
soporte_ctrl = SoporteController()


# ──────────────────────────────────────────
# Rutas del Staff (Admin y Recepcionista)
# ──────────────────────────────────────────

@soporte_bp.route("/panel")
@login_required
@rol_requerido("administrador", "recepcionista")
def panel():
    """Panel principal de gestión de chats de soporte."""
    datos_chats = soporte_ctrl.listar_chats()
    chat_activo = soporte_ctrl.agente_tiene_chat_en_progreso(session["usuario_id"])

    return render_template(
        "soporte/panel.html",
        sin_atender=datos_chats["sin_atender"],
        en_progreso=datos_chats["en_progreso"],
        total=datos_chats["total"],
        chat_activo=chat_activo,
    )


@soporte_bp.route("/chat/<int:id_chat>")
@login_required
@rol_requerido("administrador", "recepcionista")
def ver_chat(id_chat: int):
    """Vista detallada de la sala de chat de soporte."""
    chat = soporte_ctrl.obtener_chat_por_id(id_chat)
    if not chat:
        flash("La conversación ya no existe o fue finalizada.", "info")
        return redirect(url_for("soporte.panel"))

    mensajes = soporte_ctrl.obtener_mensajes(id_chat)
    chat_activo = soporte_ctrl.agente_tiene_chat_en_progreso(session["usuario_id"])

    es_mi_chat = (chat["id_usuario_atendiendo"] == session["usuario_id"])
    puede_atender = (chat["estado"] == "sin_atender" and (not chat_activo or chat_activo["id_chat"] == id_chat))

    return render_template(
        "soporte/chat.html",
        chat=chat,
        mensajes=mensajes,
        es_mi_chat=es_mi_chat,
        puede_atender=puede_atender,
        chat_activo=chat_activo,
    )


@soporte_bp.route("/chat/<int:id_chat>/tomar", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def tomar_chat(id_chat: int):
    """Asigna la conversación al operador actual si cumple las reglas."""
    ok, mensaje = soporte_ctrl.tomar_chat(
        id_chat=id_chat,
        id_usuario=session["usuario_id"],
        nombre_usuario=session.get("nombre", "Operador"),
    )

    if ok:
        flash("Has tomado la conversación. Ahora podés responder al cliente.", "success")
        return redirect(url_for("soporte.ver_chat", id_chat=id_chat))
    else:
        flash(mensaje, "warning")
        return redirect(url_for("soporte.panel"))


@soporte_bp.route("/chat/<int:id_chat>/mensaje", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def enviar_mensaje_staff(id_chat: int):
    """Envía un mensaje como operador de soporte."""
    texto = request.form.get("mensaje") or (request.json.get("mensaje") if request.is_json else "")
    if not texto or not texto.strip():
        if request.is_json:
            return jsonify({"ok": False, "error": "El mensaje no puede estar vacío"}), 400
        return redirect(url_for("soporte.ver_chat", id_chat=id_chat))

    chat = soporte_ctrl.obtener_chat_por_id(id_chat)
    if not chat:
        if request.is_json:
            return jsonify({"ok": False, "error": "El chat fue finalizado"}), 404
        flash("La conversación ya fue finalizada.", "info")
        return redirect(url_for("soporte.panel"))

    # Si el chat está sin atender y este usuario no tiene otro chat, lo toma automáticamente
    if chat["estado"] == "sin_atender":
        ok, msg = soporte_ctrl.tomar_chat(id_chat, session["usuario_id"], session.get("nombre", "Operador"))
        if not ok:
            if request.is_json:
                return jsonify({"ok": False, "error": msg}), 403
            flash(msg, "warning")
            return redirect(url_for("soporte.ver_chat", id_chat=id_chat))

    nuevo_msg = soporte_ctrl.enviar_mensaje(
        id_chat=id_chat,
        remitente_tipo="soporte",
        remitente_nombre=session.get("nombre", "Operador"),
        mensaje=texto.strip(),
    )

    if request.is_json:
        return jsonify({
            "ok": True,
            "mensaje": {
                "id_mensaje": nuevo_msg["id_mensaje"],
                "remitente_tipo": nuevo_msg["remitente_tipo"],
                "remitente_nombre": nuevo_msg["remitente_nombre"],
                "mensaje": nuevo_msg["mensaje"],
                "fecha_envio": nuevo_msg["fecha_envio"].strftime("%H:%M") if hasattr(nuevo_msg["fecha_envio"], "strftime") else str(nuevo_msg["fecha_envio"]),
            } if nuevo_msg else None
        })

    return redirect(url_for("soporte.ver_chat", id_chat=id_chat))


@soporte_bp.route("/chat/<int:id_chat>/finalizar", methods=["POST"])
@login_required
@rol_requerido("administrador", "recepcionista")
def finalizar_chat_staff(id_chat: int):
    """Finaliza y elimina la conversación de la base de datos."""
    soporte_ctrl.finalizar_chat(id_chat)
    flash("Conversación finalizada y eliminada para liberar espacio.", "success")
    return redirect(url_for("soporte.panel"))


@soporte_bp.route("/api/chat/<int:id_chat>/mensajes")
@login_required
@rol_requerido("administrador", "recepcionista")
def api_chat_mensajes_staff(id_chat: int):
    """Polling de mensajes en tiempo real para el panel del operador."""
    chat = soporte_ctrl.obtener_chat_por_id(id_chat)
    if not chat:
        return jsonify({"ok": True, "finalizado": True, "mensajes": []})

    raw_mensajes = soporte_ctrl.obtener_mensajes(id_chat)
    mensajes = []
    for m in raw_mensajes:
        fecha_str = m["fecha_envio"].strftime("%H:%M") if hasattr(m["fecha_envio"], "strftime") else str(m["fecha_envio"])
        mensajes.append({
            "id_mensaje": m["id_mensaje"],
            "remitente_tipo": m["remitente_tipo"],
            "remitente_nombre": m["remitente_nombre"],
            "mensaje": m["mensaje"],
            "fecha_envio": fecha_str,
        })

    return jsonify({
        "ok": True,
        "finalizado": False,
        "estado": chat["estado"],
        "id_usuario_atendiendo": chat["id_usuario_atendiendo"],
        "nombre_usuario_atendiendo": chat["nombre_usuario_atendiendo"],
        "mensajes": mensajes,
    })


# ──────────────────────────────────────────
# API Pública para el Cliente (Tracking / Web)
# ──────────────────────────────────────────

@soporte_bp.route("/api/iniciar", methods=["POST"])
def api_cliente_iniciar():
    """Inicia o recupera una conversación de soporte para el cliente."""
    data = request.get_json(silent=True) or request.form
    session_id = data.get("session_id") or str(uuid.uuid4())
    cliente_nombre = data.get("cliente_nombre") or "Cliente"
    nro_guia = data.get("nro_guia") or None
    cliente_email = data.get("cliente_email") or None
    mensaje_inicial = data.get("mensaje") or None

    chat = soporte_ctrl.obtener_o_crear_chat(
        session_id=session_id,
        cliente_nombre=cliente_nombre,
        nro_guia=nro_guia,
        cliente_email=cliente_email,
        mensaje_inicial=mensaje_inicial,
    )

    return jsonify({
        "ok": True,
        "session_id": chat["session_id"],
        "id_chat": chat["id_chat"],
        "estado": chat["estado"],
        "agente": chat["nombre_usuario_atendiendo"],
    })


@soporte_bp.route("/api/mensajes", methods=["GET"])
def api_cliente_mensajes():
    """Obtiene los mensajes del chat del cliente mediante su session_id."""
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"ok": False, "error": "Falta session_id"}), 400

    chat = soporte_ctrl.obtener_chat_por_session(session_id)
    if not chat:
        # Si ya no existe en la BD, fue finalizado y eliminado por soporte
        return jsonify({"ok": True, "finalizado": True, "mensajes": []})

    raw_mensajes = soporte_ctrl.obtener_mensajes(chat["id_chat"])
    mensajes = []
    for m in raw_mensajes:
        fecha_str = m["fecha_envio"].strftime("%H:%M") if hasattr(m["fecha_envio"], "strftime") else str(m["fecha_envio"])
        mensajes.append({
            "id_mensaje": m["id_mensaje"],
            "remitente_tipo": m["remitente_tipo"],
            "remitente_nombre": m["remitente_nombre"],
            "mensaje": m["mensaje"],
            "fecha_envio": fecha_str,
        })

    return jsonify({
        "ok": True,
        "finalizado": False,
        "estado": chat["estado"],
        "agente": chat["nombre_usuario_atendiendo"],
        "mensajes": mensajes,
    })


@soporte_bp.route("/api/enviar", methods=["POST"])
def api_cliente_enviar():
    """Envía un mensaje desde la interfaz del cliente."""
    data = request.get_json(silent=True) or request.form
    session_id = data.get("session_id")
    texto = data.get("mensaje")
    cliente_nombre = data.get("cliente_nombre") or "Cliente"

    if not session_id or not texto or not texto.strip():
        return jsonify({"ok": False, "error": "Datos incompletos"}), 400

    chat = soporte_ctrl.obtener_chat_por_session(session_id)
    if not chat:
        return jsonify({"ok": False, "finalizado": True, "error": "La conversación ha finalizado."}), 404

    nuevo_msg = soporte_ctrl.enviar_mensaje(
        id_chat=chat["id_chat"],
        remitente_tipo="cliente",
        remitente_nombre=cliente_nombre,
        mensaje=texto.strip(),
    )

    return jsonify({
        "ok": True,
        "id_mensaje": nuevo_msg["id_mensaje"] if nuevo_msg else None,
    })


@soporte_bp.route("/api/finalizar", methods=["POST"])
def api_cliente_finalizar():
    """El cliente decide terminar su conversación."""
    data = request.get_json(silent=True) or request.form
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"ok": False, "error": "Falta session_id"}), 400

    chat = soporte_ctrl.obtener_chat_por_session(session_id)
    if chat:
        soporte_ctrl.finalizar_chat(chat["id_chat"])

    return jsonify({"ok": True, "mensaje": "Conversación finalizada y eliminada."})
