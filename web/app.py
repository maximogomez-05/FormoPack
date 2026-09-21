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

from flask import Flask, redirect, url_for, request, send_from_directory
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
    app.config["POD_UPLOAD_DIR"] = os.path.join(ROOT, "web", "static", "uploads", "pod")
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    Session(app)

    # Registrar blueprints (rutas)
    from web.routes.auth import auth_bp
    from web.routes.recepcion import recepcion_bp
    from web.routes.admin import admin_bp
    from web.routes.chofer import chofer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(recepcion_bp, url_prefix="/recepcion")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(chofer_bp)

    # Ruta raíz → redirige según contexto
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.route("/service-worker.js")
    def service_worker():
        """Sirve el worker desde la raíz para que controle /chofer."""
        return send_from_directory(os.path.join(ROOT, "web", "static"), "service-worker.js")

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

    # ──────────────────────────────────────────
    # Handlers de error — páginas amigables
    # ──────────────────────────────────────────
    from flask import render_template_string

    _ERROR_PAGE = """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Error {{ code }} — FormoPack</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
      body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:var(--bg-body,#f4f6f9);}
      .err-card{background:#fff;border-radius:12px;padding:48px 40px;text-align:center;max-width:440px;box-shadow:0 4px 20px rgba(0,0,0,0.08);}
      .err-code{font-size:72px;font-weight:800;color:#004481;line-height:1;}
      .err-title{font-size:20px;font-weight:700;margin:12px 0 8px;color:#333;}
      .err-msg{color:#6c757d;font-size:14px;margin-bottom:24px;}
      .btn-back{background:#004481;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-size:14px;}
    </style></head><body>
    <div class="err-card">
      <div class="err-code">{{ code }}</div>
      <div class="err-title">{{ title }}</div>
      <div class="err-msg">{{ message }}</div>
      <a href="/" class="btn-back"><i class="fa-solid fa-house"></i> Volver al inicio</a>
    </div></body></html>"""

    @app.errorhandler(404)
    def not_found(e):
        return render_template_string(_ERROR_PAGE,
            code=404, title="Página no encontrada",
            message="La dirección que buscás no existe en el sistema."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template_string(_ERROR_PAGE,
            code=403, title="Acceso denegado",
            message="No tenés permisos para acceder a esta sección."), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template_string(_ERROR_PAGE,
            code=500, title="Error interno del servidor",
            message="Algo falló en el sistema. Si el problema persiste, reiniciá la aplicación."), 500

    @app.errorhandler(413)
    def too_large(e):
        return render_template_string(_ERROR_PAGE,
            code=413, title="Archivo demasiado grande",
            message="El archivo que intentás subir supera el límite de 5 MB permitido."), 413

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, host="0.0.0.0", port=5000)
