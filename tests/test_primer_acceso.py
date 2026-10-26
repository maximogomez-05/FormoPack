"""Primer acceso obligatorio y actividad compacta, con datos aislados."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest

from app.controllers.auth_controller import AuthController
from app.controllers.usuario_controller import UsuarioController
from app.services.actividad_operativa import ActividadOperativa
from app.utils.exceptions import AuthenticationError, ValidationError, DatabaseQueryError
from tests.test_regresion_paginas import aplicacion, db
from tests.test_recepcion_bd import cliente
from tests.test_seguridad_bd import ROOT


def nueva_cuenta(db, rol="recepcionista"):
    with patch("app.core.database.DatabaseManager.get_instance", return_value=db):
        UsuarioController().crear_usuario("Persona Nueva", "nueva@example.com", rol, "Provisoria123")
    return AuthController(db).login("nueva@example.com", "Provisoria123").usuario


def autenticar(app):
    c = app.test_client()
    import re
    pagina = c.get("/").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^\"]+)"', pagina).group(1)
    respuesta = c.post("/login", data={"csrf_token": token, "email": "nueva@example.com", "password": "Provisoria123"})
    assert respuesta.status_code == 302 and respuesta.location.endswith("/primer-acceso")
    return c


@pytest.mark.parametrize("rol", ["administrador", "recepcionista", "chofer"])
def test_todos_los_roles_nuevos_requieren_clave_personal(db, rol):
    assert nueva_cuenta(db, rol).debe_cambiar_password


def test_cambio_revoca_clave_provisoria_y_flag(db):
    usuario = nueva_cuenta(db)
    nuevo = AuthController(db).cambiar_password_inicial(usuario.id_usuario, 0, "Provisoria123", "PersonalNueva456", "PersonalNueva456")
    assert not nuevo.debe_cambiar_password and nuevo.version_sesion == 1
    assert AuthController(db).login("nueva@example.com", "PersonalNueva456").success
    with pytest.raises(AuthenticationError):
        AuthController(db).login("nueva@example.com", "Provisoria123")


@pytest.mark.parametrize("actual,nueva,confirmacion", [
    ("erronea", "PersonalNueva456", "PersonalNueva456"),
    ("Provisoria123", "Provisoria123", "Provisoria123"),
    ("Provisoria123", "1234", "1234"),
    ("Provisoria123", "PersonalNueva456", "Diferente123"),
])
def test_rechazos_no_consumen_clave_provisoria(db, actual, nueva, confirmacion):
    usuario = nueva_cuenta(db)
    with pytest.raises(ValidationError):
        AuthController(db).cambiar_password_inicial(usuario.id_usuario, 0, actual, nueva, confirmacion)
    assert AuthController(db).login("nueva@example.com", "Provisoria123").usuario.debe_cambiar_password


def test_url_api_y_sesion_de_otro_navegador_no_evaden_restriccion(aplicacion, db):
    nueva_cuenta(db)
    primero, segundo = autenticar(aplicacion), autenticar(aplicacion)
    assert primero.get("/admin/dashboard").location.endswith("/primer-acceso")
    assert primero.get("/recepcion/caja").location.endswith("/primer-acceso")
    api = primero.get("/recepcion/clientes/buscar?dni=12345678", headers={"X-Requested-With": "XMLHttpRequest"})
    assert api.status_code == 423 and api.json["code"] == "PASSWORD_CHANGE_REQUIRED"
    pagina = primero.get("/primer-acceso").get_data(as_text=True)
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
    with primero.session_transaction() as s: sid_antes = s.sid
    respuesta = primero.post("/primer-acceso", data={"csrf_token": token, "password_actual": "Provisoria123",
        "nueva_password": "PersonalNueva456", "confirmar_password": "PersonalNueva456"})
    assert respuesta.status_code == 302
    with primero.session_transaction() as s:
        assert not s["debe_cambiar_password"] and s.sid != sid_antes
    assert primero.get("/admin/dashboard").status_code == 200
    assert segundo.get("/admin/dashboard").status_code == 302
    with segundo.session_transaction() as s: assert "usuario_id" not in s


def test_dos_cambios_simultaneos_solo_uno_gana(db):
    usuario = nueva_cuenta(db)
    b = Barrier(2)
    def cambiar(n):
        b.wait(timeout=10)
        try:
            AuthController(db).cambiar_password_inicial(usuario.id_usuario, 0, "Provisoria123", f"PersonalNueva{n}99", f"PersonalNueva{n}99")
            return True
        except AuthenticationError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(cambiar, range(2))) == [False, True]


def test_fallo_sql_revierte_cambio(db):
    usuario = nueva_cuenta(db)
    with db.cursor(False) as cur:
        cur.execute("CREATE TRIGGER fallo_primer_acceso BEFORE UPDATE ON usuarios FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
    with pytest.raises(DatabaseQueryError):
        AuthController(db).cambiar_password_inicial(usuario.id_usuario, 0, "Provisoria123", "PersonalNueva456", "PersonalNueva456")
    assert AuthController(db).login("nueva@example.com", "Provisoria123").usuario.debe_cambiar_password


def test_migracion_no_altera_cuentas_existentes_y_es_repetible(db):
    with db.cursor() as cur:
        cur.execute("SELECT credenciales_hash FROM usuarios WHERE id_usuario=1")
        antes = cur.fetchone()["credenciales_hash"]
    db.ejecutar_archivo(ROOT / "scripts/migrations/008_primer_acceso.sql")
    with db.cursor() as cur:
        cur.execute("SELECT credenciales_hash,debe_cambiar_password FROM usuarios WHERE id_usuario=1")
        assert cur.fetchone() == {"credenciales_hash": antes, "debe_cambiar_password": 0}


@pytest.mark.parametrize("intentar_reutilizar", [False, True])
def test_recuperacion_por_otp_tambien_cumple_cambio_personal(db, intentar_reutilizar):
    nueva_cuenta(db)
    with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async") as correo:
        AuthController(db).solicitar_recuperacion("nueva@example.com")
    codigo = correo.call_args.args[2]
    if intentar_reutilizar:
        with pytest.raises(ValidationError):
            AuthController(db).restablecer_password("nueva@example.com", codigo, "Provisoria123", "Provisoria123")
    AuthController(db).restablecer_password("nueva@example.com", codigo, "PersonalNueva456", "PersonalNueva456")
    assert not AuthController(db).login("nueva@example.com", "PersonalNueva456").usuario.debe_cambiar_password


@pytest.mark.parametrize("campo", ["total_envios", "entregados", "fallidos", "facturado"])
def test_dia_con_cualquier_movimiento_se_conserva(campo):
    dias = [{"total_envios": 0, "entregados": 0, "fallidos": 0, "facturado": 0} for _ in range(7)]
    dias[2][campo] = 1
    actividad = ActividadOperativa(dias)
    assert len(actividad.filas()) == 1 and len(actividad.filas(True)) == 7


def test_panel_vacio_compacto_y_periodo_completo(aplicacion):
    c, _ = cliente(aplicacion)
    compacto = c.get("/admin/dashboard").get_data(as_text=True)
    assert "Sin movimientos en los últimos siete días" in compacto
    assert 'class="history-day"' not in compacto
    completo = c.get("/admin/dashboard?actividad=todos").get_data(as_text=True)
    assert completo.count('class="history-day"') == 7


def test_inicio_publico_y_operativo_en_tracking(aplicacion):
    publico = aplicacion.test_client().get("/admin/tracking").get_data(as_text=True)
    assert 'aria-label="Volver al inicio"' in publico
    c, _ = cliente(aplicacion)
    staff = c.get("/admin/tracking").get_data(as_text=True)
    assert 'href="/dashboard" aria-label="Volver al inicio"' in staff
