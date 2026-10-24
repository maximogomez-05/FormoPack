"""RF 1.3: pruebas aisladas; no usan MySQL ni envían correos reales."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.auth_controller import AuthController
from app.models.recuperacion_contrasena import RecuperacionContrasena
from app.utils.exceptions import DatabaseQueryError, ValidationError
from app.services.seguridad_recuperacion import ProtectorCodigoRecuperacion
from config.settings import AppConfig

AHORA = datetime(2026, 10, 24, 12, 0)
USUARIO = {"id_usuario": 17, "nombre": "Operador", "email": "operador@example.com", "activo": 1}


class TestRecuperacionContrasena:
    def test_generacion_y_vigencia(self):
        with patch("app.models.recuperacion_contrasena.secrets.randbelow", return_value=42) as random:
            codigo = RecuperacionContrasena.generar_codigo()
            rec = RecuperacionContrasena("a" * 64, AHORA + RecuperacionContrasena.VIGENCIA)
        random.assert_called_once_with(1_000_000)
        assert codigo == "000042"
        assert rec.expira_en == AHORA + timedelta(minutes=15)
        assert not rec.utilizado
        assert codigo not in repr(rec)

    @pytest.mark.parametrize("codigo", ["", "12345", "1234567", "abcdef", "１２３４５６", "12345é"])
    def test_formato_estricto(self, codigo):
        with pytest.raises(ValidationError):
            RecuperacionContrasena.validar_formato(codigo)

    def test_consumo_unico(self):
        rec = RecuperacionContrasena("123456", AHORA + timedelta(minutes=15))
        assert rec.validar_codigo(True, AHORA)
        rec.marcar_utilizado()
        assert rec.utilizado
        with pytest.raises(ValidationError):
            rec.validar_codigo(True, AHORA)
        with pytest.raises(ValidationError):
            rec.marcar_utilizado()

    @pytest.mark.parametrize("codigo,utilizado,minutos", [
        ("654321", False, 0), ("123456", True, 0),
        ("123456", False, 15), ("123456", False, 16),
    ])
    def test_error_generico(self, codigo, utilizado, minutos):
        rec = RecuperacionContrasena("123456", AHORA + timedelta(minutes=15), utilizado)
        with pytest.raises(ValidationError) as error:
            rec.validar_codigo(codigo == "123456", AHORA + timedelta(minutes=minutos))
        assert RecuperacionContrasena.ERROR_CODIGO in error.value.message


@pytest.fixture
def entorno():
    db = MagicMock()
    conn = db.get_connection.return_value
    cursor = conn.cursor.return_value
    with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async") as correo:
        ctrl = AuthController(db_manager=db)
        ctrl._limite_recuperacion.admitir = MagicMock(return_value=True)
        yield ctrl, conn, cursor, correo


class TestSolicitudRecuperacion:
    def test_emite_por_correo_sin_devolver_codigo(self, entorno):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [USUARIO, {"ahora": AHORA}]
        assert ctrl.solicitar_recuperacion(" OPERADOR@EXAMPLE.COM ") is None
        conn.commit.assert_called_once()
        codigo = correo.call_args.args[2]
        assert len(codigo) == 6 and codigo.isascii() and codigo.isdigit()
        consultas = cursor.execute.call_args_list
        assert consultas[0].args[1] == (USUARIO["email"],)
        assert "FOR UPDATE" in consultas[0].args[0]
        assert consultas[-1].args[1] == (17, ctrl._protector.proteger(codigo, 17), AHORA + timedelta(minutes=15))
        assert "SET utilizado = 1" in consultas[-2].args[0]
        cursor.close.assert_called_once()
        conn.close.assert_called_once()

    @pytest.mark.parametrize("fila", [None, {**USUARIO, "activo": 0}])
    def test_ausente_e_inactivo_no_revelan_estado(self, entorno, fila):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.return_value = fila
        assert ctrl.solicitar_recuperacion(USUARIO["email"]) is None
        correo.assert_not_called()
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        assert cursor.execute.call_count == 1

    @pytest.mark.parametrize("email", ["", "sin_arroba", "x@local", "a b@example.com", "x" * 101 + "@x.com"])
    def test_email_invalido_no_consulta_base(self, entorno, email):
        ctrl, conn, cursor, correo = entorno
        with pytest.raises(ValidationError):
            ctrl.solicitar_recuperacion(email)
        cursor.execute.assert_not_called()
        correo.assert_not_called()

    def test_fallo_persistencia_revierte_y_no_envia(self, entorno):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [USUARIO, {"ahora": AHORA}]
        cursor.execute.side_effect = [None, None, None, RuntimeError("fallo simulado")]
        with pytest.raises(DatabaseQueryError):
            ctrl.solicitar_recuperacion(USUARIO["email"])
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        correo.assert_not_called()
        conn.close.assert_called_once()


class TestRestablecimiento:
    @staticmethod
    def registro(**cambios):
        return {"id_recuperacion": 8, "codigo_hash": ProtectorCodigoRecuperacion(AppConfig.SECRET_KEY).proteger("123456", 17), "utilizado": 0, "intentos_fallidos": 0,
                "expira_en": AHORA + timedelta(minutes=15), "ahora": AHORA, **cambios}

    def test_cambio_y_consumo_en_misma_transaccion(self, entorno):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [USUARIO, self.registro()]
        with patch("app.controllers.auth_controller.Usuario.hashear_password", return_value="hash-seguro"):
            assert ctrl.restablecer_password(USUARIO["email"], "123456", "NuevaClave123", "NuevaClave123")
        consultas = cursor.execute.call_args_list
        assert "FOR UPDATE" in consultas[0].args[0]
        assert "FOR UPDATE" in consultas[1].args[0]
        assert consultas[2].args[1] == ("hash-seguro", 17)
        assert "SET utilizado = 1" in consultas[3].args[0]
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        correo.assert_not_called()

    @pytest.mark.parametrize("fila,registro", [
        (None, None), ({**USUARIO, "activo": 0}, None), (USUARIO, None),
        (USUARIO, {"codigo_hash": "a" * 64}), (USUARIO, {"utilizado": 1}),
        (USUARIO, {"expira_en": AHORA}),
    ])
    def test_rechazo_no_cambia_clave(self, entorno, fila, registro):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [fila, self.registro(**registro) if registro is not None else None]
        with patch("app.controllers.auth_controller.Usuario.hashear_password") as hashear:
            with pytest.raises(ValidationError) as error:
                ctrl.restablecer_password(USUARIO["email"], "123456", "NuevaClave123", "NuevaClave123")
        assert RecuperacionContrasena.ERROR_CODIGO in error.value.message
        hashear.assert_not_called()
        if registro is not None:
            conn.commit.assert_called_once()
        else:
            conn.rollback.assert_called_once()
            conn.commit.assert_not_called()
        assert not any("UPDATE usuarios" in call.args[0] for call in cursor.execute.call_args_list)
        conn.close.assert_called_once()

    def test_no_reutiliza_codigo(self, entorno):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [USUARIO, self.registro(), USUARIO, None]
        with patch("app.controllers.auth_controller.Usuario.hashear_password", return_value="hash-seguro"):
            assert ctrl.restablecer_password(USUARIO["email"], "123456", "NuevaClave123", "NuevaClave123")
            with pytest.raises(ValidationError):
                ctrl.restablecer_password(USUARIO["email"], "123456", "NuevaClave123", "NuevaClave123")
        assert conn.commit.call_count == 1

    def test_error_al_consumir_revierte_cambio_de_clave(self, entorno):
        ctrl, conn, cursor, correo = entorno
        cursor.fetchone.side_effect = [USUARIO, self.registro()]
        cursor.execute.side_effect = [None, None, None, RuntimeError("fallo al consumir")]
        with patch("app.controllers.auth_controller.Usuario.hashear_password", return_value="hash-seguro"):
            with pytest.raises(DatabaseQueryError):
                ctrl.restablecer_password(USUARIO["email"], "123456", "NuevaClave123", "NuevaClave123")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    @pytest.mark.parametrize("codigo,nueva,confirmacion", [
        ("00000", "NuevaClave123", "NuevaClave123"),
        ("123456", "NuevaClave123", "OtraClave123"),
        ("123456", "corta1", "corta1"),
    ])
    def test_datos_invalidos_no_consultan_base(self, entorno, codigo, nueva, confirmacion):
        ctrl, conn, cursor, correo = entorno
        with pytest.raises(ValidationError):
            ctrl.restablecer_password(USUARIO["email"], codigo, nueva, confirmacion)
        cursor.execute.assert_not_called()
