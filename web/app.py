"""
Servidor Flask — FormoPack Express
Punto de entrada de la aplicación web.
"""

import sys
import os
import logging

# Asegurar que el raíz del proyecto esté en el path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from flask import Flask, redirect, url_for, request
from flask_session import Session
from config.settings import AppConfig

# ──────────────────────────────────────────
# Configuración de logging
# ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app() -> Flask:
    """Factory de la aplicación Flask."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Configuración de sesión
    app.config["SECRET_KEY"] = AppConfig.SECRET_KEY
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = os.path.join(ROOT, ".flask_session")
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True

    Session(app)

    # Registrar blueprints (rutas)
    from web.routes.auth import auth_bp
    from web.routes.recepcion import recepcion_bp
    from web.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(recepcion_bp, url_prefix="/recepcion")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Ruta raíz → redirige según contexto
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    # ──────────────────────────────────────────
    # Filtros de Seguridad (Anti-Caché y Headers)
    # ──────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        # Evitar caché en rutas dinámicas (soluciona el bug de la flecha 'Atrás' post-logout)
        if request.endpoint != 'static':
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        # Protecciones estándar OWASP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, host="0.0.0.0", port=5000)
