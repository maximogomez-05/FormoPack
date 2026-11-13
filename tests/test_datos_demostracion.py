from unittest.mock import patch

import pytest

from app.services.datos_demostracion import DatosDemostracion
from app.controllers.usuario_controller import UsuarioController
from app.controllers.auth_controller import AuthController
from app.utils.exceptions import ValidationError, DuplicateError
from tests.test_regresion_paginas import aplicacion, db
from tests.test_recepcion_bd import envio


def test_demo_aditiva_repetible_sin_pagos_ni_correos(aplicacion, db):
    anterior = envio(db)
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async") as correo:
        guias = DatosDemostracion(db).cargar(1)
        assert len(guias) == 14
        assert DatosDemostracion(db).cargar(1) == []
        correo.assert_not_called()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM envios")
        assert cur.fetchone()["total"] == 15
        cur.execute("SELECT nro_guia FROM envios WHERE id_envio=%s", (anterior["id_envio"],))
        assert cur.fetchone()["nro_guia"] == anterior["nro_guia"]
        cur.execute("SELECT COUNT(DISTINCT DATE(fecha_creacion)) AS dias FROM envios")
        assert cur.fetchone()["dias"] == 7
        cur.execute("SELECT COUNT(*) AS total FROM envios WHERE id_envio<>%s AND destino_latitud IS NOT NULL AND destino_longitud IS NOT NULL", (anterior["id_envio"],))
        assert cur.fetchone()["total"] == 14
        for tabla in ("pagos", "turnos_caja", "hojas_de_ruta"):
            cur.execute("SELECT COUNT(*) AS total FROM " + tabla)
            assert cur.fetchone()["total"] == 0


def test_demo_conflicto_revierte_toda_la_carga(aplicacion, db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO clientes (dni,nombre_completo,telefono) VALUES ('90000008','Cliente existente','3704123456')")
    with pytest.raises(ValidationError):
        DatosDemostracion(db).cargar(1)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM envios")
        assert cur.fetchone()["total"] == 0
        cur.execute("SELECT COUNT(*) AS total FROM clientes")
        assert cur.fetchone()["total"] == 1
    with pytest.raises(ValidationError):
        DatosDemostracion(db).cargar(3)


def test_administrador_provisorio_no_restablece_cuenta_existente(aplicacion, db):
    ctrl = UsuarioController()
    ctrl.crear_usuario("Persona Demo", "persona@example.com", "administrador", "admin123")
    usuario = AuthController(db).login("persona@example.com", "admin123").usuario
    assert usuario.debe_cambiar_password
    with pytest.raises(DuplicateError):
        ctrl.crear_usuario("Persona Demo", "persona@example.com", "administrador", "OtraClave123")
    assert AuthController(db).login("persona@example.com", "admin123").success
