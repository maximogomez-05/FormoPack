"""Acceso del personal de mostrador a evidencias privadas de entrega."""

import base64
import io

from flask import Blueprint, abort, current_app, send_file

from app.core.database import DatabaseManager
from app.services.almacen_evidencias import AlmacenEvidencias
from app.services.evidencia_entrega import EvidenciaEntrega
from app.utils.exceptions import ValidationError
from web.routes.auth import login_required, rol_requerido


documentos_bp = Blueprint("documentos", __name__)


@documentos_bp.get("/evidencias/<int:id_intento>/<tipo>")
@login_required
@rol_requerido("administrador", "recepcionista")
def evidencia(id_intento, tipo):
    if tipo not in {"foto", "firma"}:
        abort(404)
    with DatabaseManager.get_instance().cursor() as cur:
        cur.execute("SELECT foto_remito,firma_receptor FROM intentos_entrega WHERE id_intento=%s", (id_intento,))
        intento = cur.fetchone()
    if not intento:
        abort(404)
    try:
        if tipo == "foto":
            almacen = AlmacenEvidencias(current_app.config["POD_UPLOAD_DIR"], current_app.config["POD_LEGACY_DIR"])
            ruta = almacen.localizar(intento["foto_remito"])
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[ruta.suffix]
            respuesta = send_file(ruta, mimetype=mime, as_attachment=True,
                                  download_name=f"evidencia-{id_intento}{ruta.suffix}", conditional=False, etag=False)
        else:
            firma = EvidenciaEntrega.firma(intento["firma_receptor"])
            datos = base64.b64decode(firma.split(",", 1)[1], validate=True)
            respuesta = send_file(io.BytesIO(datos), mimetype="image/png", as_attachment=True,
                                  download_name=f"firma-{id_intento}.png", conditional=False, etag=False)
    except (FileNotFoundError, ValidationError):
        abort(404)
    respuesta.headers["Cache-Control"] = "private, no-store, max-age=0"
    return respuesta
