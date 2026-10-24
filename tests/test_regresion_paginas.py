"""Recorridos de lectura con usuarios reales en una base aislada opt-in."""

import logging
from unittest.mock import patch

import pytest

from tests.test_seguridad_bd import db, ROOT
from web.app import create_app


@pytest.fixture
def aplicacion(db, tmp_path):
    # Completar el esquema, incluyendo GPS, sobre la base aleatoria de pruebas.
    db.ejecutar_archivo(ROOT / "scripts/init_database.sql")
    with patch("app.core.database.DatabaseManager.get_instance", return_value=db), patch("web.app.ROOT", str(tmp_path)):
        app = create_app()
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        yield app


@pytest.mark.parametrize("usuario,ruta,estado", [
    (None, "/", 200),
    (None, "/admin/tracking", 200),
    (None, "/service-worker.js", 200),
    (1, "/admin/dashboard", 200),
    (1, "/admin/logistica", 200),
    (1, "/admin/logistica/mapa/envios", 200),
    (1, "/admin/usuarios", 200),
    (1, "/admin/liquidaciones", 200),
    (1, "/admin/comprobantes", 200),
    (1, "/admin/comprobantes/exportar.csv", 200),
    (1, "/soporte/panel", 200),
    (2, "/admin/dashboard", 200),
    (2, "/recepcion/clientes", 200),
    (2, "/recepcion/cotizador", 200),
    (2, "/recepcion/nuevo-envio", 200),
    (2, "/recepcion/caja", 200),
    (2, "/soporte/panel", 200),
    (2, "/admin/usuarios", 403),
    (3, "/chofer", 200),
    (3, "/admin/usuarios", 403),
    (3, "/soporte/panel", 403),
])
def test_paginas_y_permisos(aplicacion, usuario, ruta, estado, caplog):
    cliente = aplicacion.test_client()
    if usuario:
        with cliente.session_transaction() as sesion:
            sesion.update(usuario_id=usuario, version_sesion=0)
    with caplog.at_level(logging.ERROR):
        respuesta = cliente.get(ruta, follow_redirects=True)
    assert respuesta.status_code == estado
    # Varias rutas antiguas capturan errores y devuelven HTML 200 de respaldo.
    assert not [registro for registro in caplog.records if registro.levelno >= logging.ERROR]


def test_compilan_todas_las_plantillas(aplicacion):
    for nombre in aplicacion.jinja_env.list_templates():
        aplicacion.jinja_env.get_template(nombre)
