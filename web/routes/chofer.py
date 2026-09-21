"""Rutas operativas del chofer (RF 4.1 y RF 4.2)."""

import base64
import binascii
import logging
import uuid
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.controllers.chofer_controller import ChoferController
from app.utils.exceptions import DatabaseQueryError, ValidationError
from web.routes.auth import login_required, rol_requerido

chofer_bp = Blueprint("chofer", __name__)
logger = logging.getLogger(__name__)
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@chofer_bp.route("/chofer", methods=["GET"])
@login_required
@rol_requerido("chofer")
def panel():
    """Panel responsive con las hojas y entregas propias del chofer."""
    try:
        data = ChoferController().obtener_panel(session["usuario_id"])
        return render_template("chofer/panel.html", **data)
    except Exception as exc:
        logger.exception("Error al cargar panel del chofer")
        flash(f"No se pudo cargar tu operación: {exc}", "danger")
        return render_template("chofer/panel.html", hojas=[])


@chofer_bp.route("/chofer/hojas/<int:id_hoja_ruta>/iniciar", methods=["POST"])
@login_required
@rol_requerido("chofer")
def iniciar_hoja(id_hoja_ruta: int):
    """Inicia una hoja y registra estado en_ruta."""
    try:
        ChoferController().iniciar_hoja(session["usuario_id"], id_hoja_ruta)
        flash("Ruta iniciada. Los envíos ahora figuran en tránsito.", "success")
    except (ValidationError, DatabaseQueryError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("chofer.panel"))


@chofer_bp.route("/chofer/hojas/<int:id_hoja_ruta>/envios/<int:id_envio>/entrega", methods=["POST"])
@login_required
@rol_requerido("chofer")
def registrar_entrega(id_hoja_ruta: int, id_envio: int):
    """Registra entrega exitosa o fallida con evidencias."""
    foto_path = None
    try:
        tipo_intento = request.form.get("tipo_intento", "").strip().lower()
        dni_receptor = request.form.get("dni_receptor", "").strip() or None
        firma_receptor = request.form.get("firma_receptor", "").strip() or None
        coordenadas_gps = request.form.get("coordenadas_gps", "").strip() or None
        motivo_fallo = request.form.get("motivo_fallo", "").strip() or None
        foto = request.files.get("foto_remito")

        if foto and foto.filename:
            extension = Path(foto.filename).suffix.lower()
            if extension not in ALLOWED_PHOTO_EXTENSIONS:
                raise ValidationError(field="foto_remito", reason="Solo se aceptan JPG, PNG o WEBP")
            nombre = f"pod_{id_envio}_{uuid.uuid4().hex}{extension}"
            carpeta = Path(current_app.config["POD_UPLOAD_DIR"])
            carpeta.mkdir(parents=True, exist_ok=True)
            foto.save(carpeta / nombre)
            foto_path = f"uploads/pod/{nombre}"

        firma_receptor = _normalizar_firma(firma_receptor)
        ChoferController().registrar_entrega(
            session["usuario_id"], id_hoja_ruta, id_envio, tipo_intento,
            dni_receptor, firma_receptor, foto_path, coordenadas_gps, motivo_fallo,
        )
        if request.headers.get("X-Offline-Sync") == "1":
            return jsonify({"ok": True})
        flash("Prueba de entrega registrada correctamente.", "success")
    except (ValidationError, DatabaseQueryError) as exc:
        _eliminar_foto(foto_path)
        if request.headers.get("X-Offline-Sync") == "1":
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
    except Exception as exc:
        _eliminar_foto(foto_path)
        logger.exception("Error al registrar entrega")
        if request.headers.get("X-Offline-Sync") == "1":
            return jsonify({"ok": False, "error": "Error inesperado al sincronizar"}), 500
        flash(f"No se pudo registrar la entrega: {exc}", "danger")
    return redirect(url_for("chofer.panel"))


@chofer_bp.route("/chofer/hojas/<int:id_hoja_ruta>/envios/<int:id_envio>/devolucion", methods=["POST"])
@login_required
@rol_requerido("chofer")
def registrar_devolucion(id_hoja_ruta: int, id_envio: int):
    """Registra la devolución de un envío cuya entrega fue fallida."""
    try:
        ChoferController().registrar_devolucion(
            session["usuario_id"],
            id_hoja_ruta,
            id_envio,
            request.form.get("motivo_devolucion", ""),
        )
        flash("El envío fue marcado para devolución a origen.", "success")
    except (ValidationError, DatabaseQueryError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("chofer.panel"))


def _normalizar_firma(firma: str | None) -> str | None:
    """Acepta la firma del canvas como data URL y valida que tenga contenido."""
    if not firma:
        return None
    if not firma.startswith("data:image/") or "," not in firma:
        raise ValidationError(field="firma_receptor", reason="La firma no tiene un formato válido")
    try:
        base64.b64decode(firma.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError(field="firma_receptor", reason="La firma está dañada") from exc
    return firma


def _eliminar_foto(foto_path: str | None) -> None:
    if not foto_path:
        return
    try:
        (Path(current_app.config["POD_UPLOAD_DIR"]).parent.parent / foto_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("No se pudo eliminar evidencia temporal: %s", foto_path)
