"""Límites, criptografía y sesiones sin persistencia ni correo reales."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.auth_controller import AuthController
from app.core.database import DatabaseManager
from app.core.migrations import MigrationManager
from app.models.recuperacion_contrasena import RecuperacionContrasena
from app.models.usuario import Usuario
from app.services.seguridad_recuperacion import ProtectorCodigoRecuperacion, LimiteSolicitudesRecuperacion
from app.utils.exceptions import ValidationError, DatabaseQueryError
from tests.test_seguridad_http import app
from web.routes.auth import login_required, rol_requerido

AHORA = datetime(2026, 10, 24, 12)


class TestValidacionMigracion:
    @pytest.mark.parametrize("version", ["5", "abc", "005; DROP"])
    def test_version_invalida_no_toca_base(self, version):
        db = MagicMock()
        with pytest.raises(ValueError):
            MigrationManager(db).aplicar_migraciones(desde=version)
        db.get_connection.assert_not_called()
        db.cursor.assert_not_called()


class TestProtectorCodigo:
    def test_hmac_ligado_a_usuario_y_clave(self):
        protector = ProtectorCodigoRecuperacion("clave-privada")
        verificador = protector.proteger("123456", 17)
        assert len(verificador) == 64
        assert protector.verificar("123456", 17, verificador)
        assert not protector.verificar("123456", 18, verificador)
        assert not protector.verificar("123457", 17, verificador)
        assert not ProtectorCodigoRecuperacion("otra-clave").verificar("123456", 17, verificador)
        assert protector.clave_cuenta(" OPERADOR@EXAMPLE.COM ") == protector.clave_cuenta("operador@example.com")
        assert protector.clave_cuenta("operador@example.com") != verificador

    def test_falla_al_quinto_intento_y_no_acepta_luego_el_correcto(self):
        rec = RecuperacionContrasena("a" * 64, AHORA + timedelta(minutes=15))
        for intento in range(1, 6):
            with pytest.raises(ValidationError):
                rec.validar_codigo(False, AHORA)
            assert rec.intentos_fallidos == intento
        assert rec.utilizado
        with pytest.raises(ValidationError):
            rec.validar_codigo(True, AHORA)


class TestLimitePorCuenta:
    @pytest.mark.parametrize("solicitudes,ultimo,inicio,esperado", [
        (0, None, AHORA, True),
        (1, AHORA - timedelta(seconds=59), AHORA, False),
        (1, AHORA - timedelta(seconds=60), AHORA, True),
        (5, AHORA - timedelta(minutes=2), AHORA, False),
        (5, AHORA - timedelta(hours=1), AHORA - timedelta(hours=1), True),
    ])
    def test_presupuesto_y_limites_temporales(self, solicitudes, ultimo, inicio, esperado):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "ahora": AHORA, "solicitudes": solicitudes,
            "ultimo_envio": ultimo, "ventana_inicio": inicio,
        }
        assert LimiteSolicitudesRecuperacion().admitir(cursor, "a" * 64) is esperado
        actualizaciones = [call for call in cursor.execute.call_args_list if "UPDATE limites" in call.args[0]]
        assert bool(actualizaciones) is esperado
        if esperado and inicio < AHORA:
            assert actualizaciones[0].args[1][1] == 1

    def test_solicitud_bloqueada_no_cambia_otp_ni_envia_correo(self):
        db = MagicMock()
        ctrl = AuthController(db)
        ctrl._limite_recuperacion.admitir = MagicMock(return_value=False)
        with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async") as correo:
            assert ctrl.solicitar_recuperacion("operador@example.com") is None
        correo.assert_not_called()
        db.get_connection.return_value.cursor.return_value.execute.assert_not_called()


class TestPassword:
    @pytest.mark.parametrize("password", ["A1" + "x" * 71, "Á1" + "é" * 35])
    def test_rechaza_mas_de_72_bytes(self, password):
        with pytest.raises(ValidationError):
            Usuario.validar_complejidad_password(password)

    def test_admite_exactamente_72_bytes(self):
        Usuario.validar_complejidad_password("A1" + "x" * 70)
        Usuario.validar_complejidad_password("A1" + "é" * 35)


class TestSesionesHTTP:
    @staticmethod
    def preparar(app, fila, version=0):
        db = DatabaseManager.get_instance.return_value
        db.get_connection.return_value.cursor.return_value.fetchone.return_value = fila

        @app.route("/privado-prueba")
        @login_required
        @rol_requerido("administrador")
        def privado():
            return "permitido"

        client = app.test_client()
        with client.session_transaction() as session:
            session.update(usuario_id=17, version_sesion=version, rol="administrador")
        return client

    @staticmethod
    def usuario(**cambios):
        return {"nombre": "Operador", "email": "operador@example.com", "tipo_usuario": "administrador",
                "activo": 1, "version_sesion": 0, **cambios}

    @pytest.mark.parametrize("fila", [None, usuario(activo=0), usuario(version_sesion=1)])
    def test_sesion_revocada_no_ejecuta_operacion(self, app, fila):
        client = self.preparar(app, fila)
        response = client.get("/privado-prueba", headers={"Accept": "application/json"})
        assert response.status_code == 401
        assert response.json["code"] == "SESSION_EXPIRED"
        with client.session_transaction() as session:
            assert "usuario_id" not in session

    def test_sesion_vigente_admitida(self, app):
        client = self.preparar(app, self.usuario())
        assert client.get("/privado-prueba").status_code == 200

    @pytest.mark.parametrize("accept", ["text/html", "application/json"])
    def test_cambio_de_rol_vigente_rechaza_con_403(self, app, accept):
        client = self.preparar(app, self.usuario(tipo_usuario="chofer"))
        response = client.get("/privado-prueba", headers={"Accept": accept})
        assert response.status_code == 403
        if accept == "application/json":
            assert response.json["code"] == "FORBIDDEN"

    def test_caida_base_no_autoriza_con_datos_viejos(self, app):
        client = self.preparar(app, self.usuario())
        DatabaseManager.get_instance.return_value.get_connection.return_value.cursor.side_effect = RuntimeError("offline")
        response = client.get("/privado-prueba", headers={"Accept": "application/json"})
        assert response.status_code == 503
        assert response.json["code"] == "SERVICE_UNAVAILABLE"

    def test_login_renueva_sid_y_elimina_datos_previos(self, app):
        app.config["WTF_CSRF_ENABLED"] = False
        client = app.test_client()
        with client.session_transaction() as session:
            session["recuperar_email"] = "anterior@example.com"
            sid_anterior = session.sid
        usuario = Usuario(17, "Operador", "operador@example.com", "hash", "administrador", version_sesion=3)
        with patch("web.routes.auth.AuthController") as auth:
            auth.return_value.login.return_value = SimpleNamespace(usuario=usuario, rol="administrador")
            response = client.post("/login", data={"email": usuario.email, "password": "Clave1234"})
        assert response.status_code == 302
        with client.session_transaction() as session:
            assert session.sid != sid_anterior
            assert session["version_sesion"] == 3
            assert "recuperar_email" not in session
        anterior = app.test_client()
        anterior.set_cookie("session", sid_anterior)
        with anterior.session_transaction() as session:
            assert "usuario_id" not in session
