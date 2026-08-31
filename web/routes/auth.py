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
@auth_bp.route("/login", methods=["GET", "POST"])
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

    return render_template("login.html")


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    """Redirige al dashboard según el rol del usuario."""
    rol = session.get("rol", "")
    if rol == "administrador":
        return redirect(url_for("admin.dashboard"))
    elif rol == "recepcionista":
        return redirect(url_for("recepcion.inicio"))
    elif rol == "chofer":
        # Por ahora, chofer ve un mensaje simple hasta tener su módulo
        return render_template("chofer_placeholder.html")
    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Cierra la sesión del usuario."""
    nombre = session.get("nombre", "Usuario")
    session.clear()
    flash(f"Sesión cerrada. ¡Hasta luego, {nombre}!", "info")
    return redirect(url_for("auth.login"))
