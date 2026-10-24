"""Regresiones HTTP de recuperación y CSRF sin servicios externos."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.database import DatabaseManager
from app.controllers.auth_controller import AuthController
from web.app import create_app
from web.extensions import limiter


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Aislar cualquier acceso de las rutas a la base configurada.
    monkeypatch.setattr(DatabaseManager, "get_instance", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("web.app.ROOT", str(tmp_path))
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-only-security-key", SESSION_COOKIE_SECURE=False)
    limiter.reset()
    yield app
    limiter.reset()


class TestRecuperacionHTTP:
    def test_misma_respuesta_para_cuentas_activas_ausentes_e_inactivas(self, app):
        from datetime import datetime

        app.config["WTF_CSRF_ENABLED"] = False
        respuestas = []
        for usuario in (
            {"id_usuario": 17, "email": "operador@example.com", "nombre": "Operador", "activo": 1},
            None,
            {"id_usuario": 17, "activo": 0},
        ):
            db = MagicMock()
            db.get_connection.return_value.cursor.return_value.fetchone.side_effect = [
                usuario, {"ahora": datetime(2026, 10, 24, 12)},
            ]
            with patch("app.services.seguridad_recuperacion.LimiteSolicitudesRecuperacion.admitir", return_value=True), \
                 patch("web.routes.auth.AuthController", return_value=AuthController(db)), \
                 patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async"):
                client = app.test_client()
                response = client.post("/recuperar-password", data={"email": "operador@example.com"})
                with client.session_transaction() as session:
                    respuestas.append((response.status_code, response.headers.get("Location"), session["_flashes"]))
        assert respuestas[0] == respuestas[1] == respuestas[2]

    @pytest.mark.parametrize("smtp", [False, True])
    def test_no_expone_otp_aunque_no_haya_smtp(self, app, smtp):
        app.config["WTF_CSRF_ENABLED"] = False
        with patch("web.routes.auth.AuthController") as auth, \
             patch("config.settings.EmailConfig.USER", "correo@example.com" if smtp else ""), \
             patch("config.settings.EmailConfig.PASSWORD", "test-only" if smtp else ""):
            # Ni siquiera una regresión del controlador debe exponer su retorno.
            auth.return_value.solicitar_recuperacion.return_value = ({}, "654321")
            client = app.test_client()
            response = client.post("/recuperar-password", data={"email": "operador@example.com"})
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/restablecer-password")
            with client.session_transaction() as session:
                mensajes = str(session.get("_flashes", []))
                assert "Si el correo corresponde a una cuenta habilitada" in mensajes
                assert "654321" not in str(dict(session))
            response = client.get(response.headers["Location"])
            assert b"654321" not in response.data

    def test_get_formularios(self, app):
        client = app.test_client()
        for ruta in ("/recuperar-password", "/restablecer-password"):
            response = client.get(ruta)
            assert response.status_code == 200
            assert b'csrf_token' in response.data


class TestErroresSeguridadHTTP:
    def test_csrf_html_devuelve_400_sin_error_interno_ni_redireccion(self, app):
        with patch("web.routes.auth.AuthController") as auth:
            response = app.test_client().post(
                "/recuperar-password", data={"email": "operador@example.com"},
                headers={"Referer": "https://sitio-ajeno.example/"},
            )
        assert response.status_code == 400
        assert "Location" not in response.headers
        assert "Solicitud no completada" in response.get_data(as_text=True)
        assert 'href="/recuperar-password"' in response.get_data(as_text=True)
        assert "sitio-ajeno" not in response.get_data(as_text=True)
        auth.assert_not_called()

    @pytest.mark.parametrize("headers,datos", [
        ({"Accept": "application/json"}, {}),
        ({"X-Offline-Sync": "1"}, {}),
        ({"X-Requested-With": "XMLHttpRequest"}, {}),
        ({"Content-Type": "application/json"}, '{"latitud": -26}'),
    ])
    def test_csrf_api_y_offline_no_simula_exito(self, app, headers, datos):
        response = app.test_client().post(
            "/chofer/hojas/1/ubicacion", data=datos, headers=headers,
        )
        assert response.status_code == 400
        assert response.json["ok"] is False
        assert response.json["code"] == "CSRF_ERROR"

    def test_webhook_no_dispara_nameerror_en_error_csrf(self, app):
        # La autenticación y exención del webhook se resuelven en la etapa de pagos.
        with patch("web.routes.recepcion.MercadoPagoService") as mp:
            response = app.test_client().post("/recepcion/mp/webhook", json={"type": "payment"})
        assert response.status_code == 400
        assert response.json["code"] == "CSRF_ERROR"
        mp.assert_not_called()

    @pytest.mark.parametrize("accept", ["text/html", "application/json"])
    def test_limite_conserva_http_429(self, app, accept):
        @app.route("/limite-prueba")
        @limiter.limit("1 per minute")
        def limitada():
            return "ok"

        client = app.test_client()
        assert client.get("/limite-prueba").status_code == 200
        response = client.get("/limite-prueba", headers={"Accept": accept})
        assert response.status_code == 429
        assert "Location" not in response.headers
        if accept == "application/json":
            assert response.json["ok"] is False
            assert response.json["code"] == "RATE_LIMIT_EXCEEDED"

    def test_csrf_valido_permite_procesar_formulario(self, app):
        import re

        client = app.test_client()
        pagina = client.get("/recuperar-password").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
        with patch("web.routes.auth.AuthController") as auth:
            auth.return_value.solicitar_recuperacion.return_value = None
            response = client.post("/recuperar-password", data={
                "email": "operador@example.com", "csrf_token": token,
            })
        assert response.status_code == 302
        auth.return_value.solicitar_recuperacion.assert_called_once_with("operador@example.com")
