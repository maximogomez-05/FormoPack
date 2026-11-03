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
    (3, "/admin/dashboard", 403),
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

def test_dashboard_distingue_fallo_de_indicadores_de_dia_sin_movimiento(aplicacion, monkeypatch):
    from web.routes import admin
    leer = admin._obtener_metricas

    def fallo_de_lectura():
        with patch.object(admin.DatabaseManager, "get_instance", side_effect=RuntimeError("lectura interrumpida")):
            return leer()

    monkeypatch.setattr(admin, "_obtener_metricas", fallo_de_lectura)
    cliente = aplicacion.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=1, version_sesion=0)
    respuesta = cliente.get("/admin/dashboard")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "No se pudieron cargar los indicadores" in html
    assert "Valor de envíos registrados hoy" not in html

def test_dashboard_separa_pendientes_vacios_de_error(aplicacion, monkeypatch):
    from web.routes import admin

    cliente = aplicacion.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=2, version_sesion=0)
    vacio = cliente.get("/admin/dashboard").get_data(as_text=True)
    assert "Sin pendientes de despacho" in vacio
    assert "Sin movimientos en los últimos siete días" in vacio

    monkeypatch.setattr(admin, "_obtener_pendientes_operativos", lambda: {"error": True})
    monkeypatch.setattr(admin, "construir_alertas_operativas", lambda _: [
        {"guia": "FP-PRUEBA", "mensaje": "Visita pendiente", "tipo": "warning"}
    ])
    html = cliente.get("/admin/dashboard").get_data(as_text=True)
    assert "No se pudieron cargar los pendientes" in html
    assert "Sin pendientes de despacho" not in html
    assert "Dinero cobrado hoy" in html
    assert "Visita pendiente" in html
    assert "Notificar por Gmail" not in html
