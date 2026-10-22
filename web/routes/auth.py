"""
Rutas de Autenticación — Login / Logout
Blueprint: auth_bp
"""

import logging
from functools import wraps
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash,
)

from app.controllers.auth_controller import AuthController
from app.utils.exceptions import (
    AuthenticationError, UserNotFoundError,
    UserInactiveError, ValidationError,
    DatabaseConnectionError,
)
from web.extensions import limiter

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# Decorador de protección de rutas
# ──────────────────────────────────────────
def login_required(f):
    """Decorador: redirige al login si no hay sesión activa."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debés iniciar sesión para acceder.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def rol_requerido(*roles):
    """Decorador: verifica que el usuario tenga el rol correcto."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "usuario_id" not in session:
                return redirect(url_for("auth.login"))
            if session.get("rol") not in roles:
                flash("No tenés permisos para acceder a esa sección.", "danger")
                return redirect(url_for("auth.dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ──────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────
@auth_bp.route("/")
def landing():
    """Página de presentación pública del sistema."""
    if "usuario_id" in session:
        return redirect(url_for("auth.dashboard"))
    return render_template("landing.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    """Pantalla de inicio de sesión."""
    # Si ya está logueado, redirigir directo
    if "usuario_id" in session:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            auth = AuthController()
            resultado = auth.login(email, password)

            # Guardar sesión
            session["usuario_id"] = resultado.usuario.id_usuario
            session["nombre"] = resultado.usuario.nombre
            session["email"] = resultado.usuario.email
            session["rol"] = resultado.usuario.tipo_usuario

            logger.info("Login exitoso: %s (%s)", email, resultado.rol)
            flash(f"Bienvenido, {resultado.usuario.nombre}!", "success")
            return redirect(url_for("auth.dashboard"))

        except (UserNotFoundError, AuthenticationError):
            flash("Email o contraseña incorrectos.", "danger")
        except UserInactiveError:
            flash("Tu cuenta está inactiva. Contactá al administrador.", "warning")
        except ValidationError as e:
            flash(str(e.message), "warning")
        except DatabaseConnectionError:
            flash("No se puede conectar a la base de datos. Verificá que MySQL esté activo.", "danger")
        except Exception as e:
            logger.error("Error inesperado en login: %s", e)
            flash("Ocurrió un error inesperado. Intentá de nuevo.", "danger")

        # Si hubo un error en POST, redirigir a la landing (que abrirá el modal por los flash messages)
        return redirect(url_for('auth.landing'))

    # Si alguien entra a /login por GET directo, lo mandamos a la landing
    return redirect(url_for('auth.landing'))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    """Redirige al dashboard según el rol del usuario."""
    rol = session.get("rol", "")
    if rol in ("administrador", "recepcionista"):
        return redirect(url_for("admin.dashboard"))
    elif rol == "chofer":
        return redirect(url_for("chofer.panel"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Cierra la sesión del usuario."""
    nombre = session.get("nombre", "Usuario")
    session.clear()
    flash(f"Sesión cerrada. ¡Hasta luego, {nombre}!", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/recuperar-password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def recuperar_password():
    """Solicitud de código de 6 dígitos para recuperación de contraseña."""
    if "usuario_id" in session:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        try:
            auth = AuthController()
            fila, codigo = auth.solicitar_recuperacion(email)
            session["recuperar_email"] = email

            from config.settings import EmailConfig
            if not EmailConfig.USER or not EmailConfig.PASSWORD:
                flash(f"Se generó el código de recuperación para {email}. Código de verificación de prueba: {codigo} (Válido por 15 minutos).", "info")
            else:
                flash(f"Enviamos un código de 6 dígitos a {email}. Revisá tu casilla de correo.", "success")
            return redirect(url_for("auth.restablecer_password"))
        except ValidationError as e:
            flash(str(e.message), "danger")
        except UserInactiveError as e:
            flash(str(e.message), "warning")
        except Exception as e:
            logger.exception("Error al solicitar recuperación de contraseña para %s", email)
            flash("Ocurrió un error inesperado al procesar la solicitud. Intentá de nuevo.", "danger")

    return render_template("auth/recuperar_password.html")


@auth_bp.route("/restablecer-password", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def restablecer_password():
    """Verificación de código de 6 dígitos y asignación de nueva contraseña."""
    if "usuario_id" in session:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        codigo = request.form.get("codigo", "").strip()
        nueva_password = request.form.get("nueva_password", "")
        confirmar_password = request.form.get("confirmar_password", "")

        try:
            auth = AuthController()
            auth.restablecer_password(email, codigo, nueva_password, confirmar_password)
            session.pop("recuperar_email", None)
            flash("¡Tu contraseña ha sido restablecida exitosamente! Ya podés ingresar con tu nueva clave.", "success")
            return redirect(url_for("auth.landing"))
        except ValidationError as e:
            flash(str(e.message), "danger")
        except UserInactiveError as e:
            flash(str(e.message), "warning")
        except Exception as e:
            logger.exception("Error al restablecer contraseña para %s", email)
            flash("Ocurrió un error inesperado al actualizar la contraseña.", "danger")

    email_precargado = session.get("recuperar_email", request.args.get("email", ""))
    return render_template("auth/restablecer_password.html", email=email_precargado)

