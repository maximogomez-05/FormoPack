"""Edición exclusiva del perfil personal."""

import io
from mysql.connector import Error as MySQLError

from flask import abort, Blueprint, Response, flash, redirect, render_template, request, send_file, session, url_for

from app.services.perfil_usuario import PerfilUsuario
from app.utils.exceptions import AuthenticationError, ValidationError
from web.extensions import limiter
from web.routes.auth import login_required, rol_requerido


perfil_bp = Blueprint("perfil", __name__)


@perfil_bp.errorhandler(MySQLError)
def fallo_persistencia(error):
    from web.security.error_handlers import ManejadorErroresSeguridad
    return ManejadorErroresSeguridad().error_persistencia(error)


@perfil_bp.route("/", methods=["GET", "POST"])
@login_required
def editar():
    servicio = PerfilUsuario()
    error = None
    if request.method == "POST":
        try:
            session["nombre"] = servicio.guardar_datos(
                session["usuario_id"], session["version_sesion"], request.form.get("nombre", ""),
                request.form.get("nro_licencia", ""))
            flash("Tus datos quedaron guardados.", "success")
            return redirect(url_for("perfil.editar"))
        except ValidationError as exc:
            error = exc.message
    return render_template("perfil.html", perfil=servicio.obtener(session["usuario_id"]), error=error), 400 if error else 200


@perfil_bp.post("/password")
@login_required
@limiter.limit("5 per minute")
def password():
    try:
        PerfilUsuario().cambiar_password(
            session["usuario_id"], session["version_sesion"], request.form.get("password_actual", ""),
            request.form.get("password", ""), request.form.get("confirmacion", ""))
    except ValidationError as exc:
        return render_template("perfil.html", perfil=PerfilUsuario().obtener(session["usuario_id"]),
                               error=exc.message), 400
    session.clear()
    # Eliminar el identificador anterior aunque el usuario cierre esta pestaña.
    session["salida"] = True
    from flask import current_app
    current_app.session_interface.regenerate(session)
    session.clear()
    flash("Contraseña actualizada. Ingresá con tu nueva contraseña.", "success")
    return redirect(url_for("auth.login"))


@perfil_bp.route("/foto", methods=["GET", "POST"])
@login_required
def foto():
    servicio = PerfilUsuario()
    if request.method == "POST":
        try:
            if request.form.get("quitar") == "1":
                servicio.quitar_foto(session["usuario_id"], session["version_sesion"])
            else:
                archivo = request.files.get("foto")
                if not archivo or not archivo.filename:
                    raise ValidationError("foto", "Elegí una foto")
                servicio.guardar_foto(session["usuario_id"], session["version_sesion"], archivo.stream)
            flash("Foto de perfil actualizada.", "success")
            return redirect(url_for("perfil.editar"))
        except ValidationError as exc:
            return render_template("perfil.html", perfil=servicio.obtener(session["usuario_id"]),
                                   error=exc.message), 400
    imagen = servicio.foto(session["usuario_id"])
    if imagen:
        return send_file(io.BytesIO(imagen), mimetype="image/png", conditional=False, etag=False)
    from html import escape
    inicial = escape((session.get("nombre") or "U")[0].upper())
    return Response(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                    f'<rect width="64" height="64" rx="32" fill="#145680"/>'
                    f'<text x="32" y="42" text-anchor="middle" font-family="sans-serif" '
                    f'font-size="30" fill="white">{inicial}</text></svg>', mimetype="image/svg+xml")


@perfil_bp.route("/cuentas/<int:identificador>", methods=["GET", "POST"])
@login_required
@rol_requerido("administrador")
def cuenta(identificador):
    if identificador == session["usuario_id"]:
        return redirect(url_for("perfil.editar"))
    abort(403)



@perfil_bp.errorhandler(AuthenticationError)
def sesion_cambiada(error):
    session.clear()
    flash("La sesión cambió. Volvé a ingresar.", "warning")
    return redirect(url_for("auth.login"))
