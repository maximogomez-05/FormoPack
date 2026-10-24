"""RF 5.6: políticas y HTTP aislados de la base operativa."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.chat_soporte import ChatSoporte, MensajeSoporte
from app.utils.exceptions import SoporteError
from app.core.database import DatabaseManager
from tests.test_seguridad_http import app


class TestPoliticasSoporte:
    @pytest.mark.parametrize("texto", [None, [], {}, 1, "", "  ", "x" * 2001, "a\x00b"])
    def test_mensaje_invalido(self, texto):
        with pytest.raises(SoporteError):
            MensajeSoporte(texto)

    def test_mensaje_valido(self):
        assert MensajeSoporte("  Consulta sobre mi envío  ").texto == "Consulta sobre mi envío"
        assert MensajeSoporte("x" * 2000).texto == "x" * 2000

    def test_admin_supervisa_pero_no_responde_por_otro(self):
        politica = ChatSoporte({"estado": "en_progreso", "id_usuario_atendiendo": 2})
        assert politica.puede_leer(1, "administrador")
        assert politica.puede_finalizar(1, "administrador")
        with pytest.raises(SoporteError):
            politica.validar_respuesta(1)
        with pytest.raises(SoporteError):
            politica.validar_lectura(3, "recepcionista")
        with pytest.raises(SoporteError):
            politica.validar_cierre(3, "recepcionista")
        politica.validar_respuesta(2)

    def test_asignacion_idempotente_y_estado_terminal(self):
        politica = ChatSoporte({"estado": "sin_atender"})
        assert politica.asignar(2)
        assert not politica.asignar(2)
        with pytest.raises(SoporteError):
            politica.asignar(3)
        cerrado = ChatSoporte({"estado": "cerrado", "id_usuario_atendiendo": 2})
        with pytest.raises(SoporteError):
            cerrado.asignar(2)
        with pytest.raises(SoporteError):
            cerrado.validar_respuesta(2)


@pytest.fixture
def ctrl():
    with patch("web.routes.soporte.SoporteController") as factory:
        yield factory.return_value


class TestSoporteHTTP:
    @staticmethod
    def autenticar(client, id_usuario=2, rol="recepcionista"):
        DatabaseManager.get_instance.return_value.get_connection.return_value.cursor.return_value.fetchone.return_value = {
            "activo": 1, "version_sesion": 0, "tipo_usuario": rol,
            "nombre": "Operador", "email": "operador@example.com",
        }
        with client.session_transaction() as sesion:
            sesion.update(usuario_id=id_usuario, rol=rol, version_sesion=0)

    @staticmethod
    def token_csrf(client):
        import re
        pagina = client.get("/admin/tracking").get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', pagina).group(1)

    def test_chat_no_inicializa_base_al_importar(self):
        from app.controllers.soporte_controller import SoporteController
        db = MagicMock()
        SoporteController(db)
        db.get_connection.assert_not_called()

    @pytest.mark.parametrize("ruta", ["/soporte/api/iniciar", "/soporte/api/enviar", "/soporte/api/finalizar", "/soporte/chat/1/tomar", "/soporte/chat/1/mensaje", "/soporte/chat/1/finalizar"])
    def test_mutaciones_exigen_csrf(self, app, ctrl, ruta):
        respuesta = app.test_client().post(ruta, json={})
        assert respuesta.status_code == 400
        assert respuesta.json["code"] == "CSRF_ERROR"
        assert ctrl.mock_calls == []

    def test_inicio_csrf_y_token_solo_en_sesion(self, app, ctrl):
        ctrl.iniciar_chat.return_value = {"id_chat": 17, "estado": "sin_atender", "nombre_usuario_atendiendo": None}
        client = app.test_client()
        token = self.token_csrf(client)
        response = client.post("/soporte/api/iniciar", json={"cliente_nombre": "Cliente", "mensaje": "Consulta"}, headers={"X-CSRFToken": token})
        assert response.status_code == 200
        assert "session_id" not in response.json
        with client.session_transaction() as sesion:
            identidad = sesion["soporte_cliente_token"]
        assert len(identidad) == 64 and identidad not in response.get_data(as_text=True)
        assert ctrl.iniciar_chat.call_args.args[0] == identidad

    @pytest.mark.parametrize("payload", [[], "texto", {"session_id": "ajeno"}, {"cliente_nombre": "Suplantado", "mensaje": "hola"}])
    def test_rechaza_payloads_que_intentan_elegir_identidad(self, app, ctrl, payload):
        app.config["WTF_CSRF_ENABLED"] = False
        response = app.test_client().post("/soporte/api/enviar", json=payload)
        assert response.status_code == 400
        ctrl.enviar_cliente.assert_not_called()

    def test_consulta_no_acepta_identificadores_en_url(self, app, ctrl):
        response = app.test_client().get("/soporte/api/mensajes?session_id=ajeno")
        assert response.status_code == 400
        ctrl.consultar_cliente.assert_not_called()

    def test_remitente_cliente_se_resuelve_en_servidor(self, app, ctrl):
        app.config["WTF_CSRF_ENABLED"] = False
        ctrl.enviar_cliente.return_value = {"id_mensaje": 7}
        client = app.test_client()
        with client.session_transaction() as sesion:
            sesion["soporte_cliente_token"] = "a" * 64
        assert client.post("/soporte/api/enviar", json={"mensaje": "Hola"}).status_code == 200
        ctrl.enviar_cliente.assert_called_once_with("a" * 64, "Hola")

    def test_staff_ajeno_no_puede_enviar_ni_finalizar(self, app, ctrl):
        app.config["WTF_CSRF_ENABLED"] = False
        client = app.test_client()
        self.autenticar(client)
        ctrl.enviar_staff.side_effect = SoporteError("Sin permiso", 403, "SUPPORT_FORBIDDEN")
        ctrl.finalizar_staff.side_effect = SoporteError("Sin permiso", 403, "SUPPORT_FORBIDDEN")
        for ruta in ("mensaje", "finalizar"):
            response = client.post(f"/soporte/chat/1/{ruta}", json={"mensaje": "hola"} if ruta == "mensaje" else {})
            assert response.status_code == 403
        ctrl.enviar_staff.assert_called_once_with(1, 2, "hola")
        ctrl.finalizar_staff.assert_called_once_with(1, 2)

    def test_polling_staff_sin_sesion_devuelve_401(self, app):
        response = app.test_client().get("/soporte/api/chat/1/mensajes")
        assert response.status_code == 401
        assert response.json["code"] == "SESSION_EXPIRED"

    def test_mensaje_staff_csrf_valido(self, app, ctrl):
        client = app.test_client()
        self.autenticar(client)
        token = self.token_csrf(client)
        ctrl.enviar_staff.return_value = {"id_mensaje": 2, "remitente_tipo": "soporte", "remitente_nombre": "Operador", "mensaje": "Hola", "fecha_envio": datetime(2026, 10, 24, 12)}
        response = client.post("/soporte/chat/1/mensaje", json={"mensaje": "Hola"}, headers={"X-CSRFToken": token})
        assert response.status_code == 200 and response.json["ok"]
        assert response.json["mensaje"]["fecha_envio"] == "12:00"

    def test_limite_inicio_es_real_y_no_simula_exito(self, app, ctrl):
        app.config["WTF_CSRF_ENABLED"] = False
        ctrl.iniciar_chat.return_value = {"id_chat": 1, "estado": "sin_atender", "nombre_usuario_atendiendo": None}
        client = app.test_client()
        for _ in range(5):
            assert client.post("/soporte/api/iniciar", json={"cliente_nombre": "Cliente"}).status_code == 200
        response = client.post("/soporte/api/iniciar", json={"cliente_nombre": "Cliente"})
        assert response.status_code == 429
        assert response.json["ok"] is False
