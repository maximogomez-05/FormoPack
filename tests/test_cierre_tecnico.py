from unittest.mock import MagicMock, patch

import pytest
from mysql.connector import Error

from app.core.database import DatabaseManager
from app.utils.exceptions import DatabaseConnectionError, DatabaseQueryError
from web.extensions import direccion_cliente
from web.app import create_app


def test_commit_fallido_no_informa_exito():
    db = object.__new__(DatabaseManager)
    conexion = MagicMock()
    conexion.commit.side_effect = Error("fallo de escritura")
    with patch.object(db, "get_connection", return_value=conexion):
        with pytest.raises(DatabaseConnectionError):
            with db.cursor() as cursor:
                cursor.execute("consulta de prueba")
    conexion.rollback.assert_called_once()
    conexion.close.assert_called_once()


def test_pool_reintenta_despues_de_fallo(monkeypatch):
    monkeypatch.setattr(DatabaseManager, "_instance", None)
    with patch.object(DatabaseManager, "_initialize_pool", side_effect=[DatabaseConnectionError("fallo"), None]) as init:
        with pytest.raises(DatabaseConnectionError):
            DatabaseManager.get_instance()
        assert DatabaseManager.get_instance() is DatabaseManager.get_instance()
        assert init.call_count == 2


@pytest.mark.parametrize("activo,origen,cabecera,esperado", [
    ("1", "127.0.0.1", "203.0.113.4", "203.0.113.4"),
    ("1", "203.0.113.2", "203.0.113.4", "203.0.113.2"),
    ("0", "127.0.0.1", "203.0.113.4", "127.0.0.1"),
    ("1", "::1", "falsa, 203.0.113.4", "::1"),
])
def test_proxy_explicito(monkeypatch, activo, origen, cabecera, esperado):
    from flask import Flask
    monkeypatch.setenv("FORMOPACK_PROXY_LOCAL", activo)
    with Flask(__name__).test_request_context("/", environ_base={"REMOTE_ADDR": origen}, headers={"X-Real-IP": cabecera}):
        assert direccion_cliente() == esperado


def test_tracking_caida_sql_responde_503(tmp_path, monkeypatch):
    monkeypatch.setattr("web.app.ROOT", str(tmp_path))
    with patch("web.routes.admin.DatabaseManager.get_instance", side_effect=DatabaseQueryError("detalle interno")):
        respuesta = create_app().test_client().get("/admin/tracking?guia=FPX-TEST")
    assert respuesta.status_code == 503
    assert b"detalle interno" not in respuesta.data
    assert b"No se encontr" not in respuesta.data


@pytest.mark.parametrize("consulta", ["_obtener_comprobantes_admin", "_obtener_envios_para_alertas"])
def test_fallo_de_consulta_no_se_presenta_como_lista_vacia(consulta):
    from web.routes import admin
    with patch.object(DatabaseManager, "get_instance", side_effect=DatabaseConnectionError("detalle privado")):
        with pytest.raises(DatabaseQueryError):
            getattr(admin, consulta)({}) if consulta == "_obtener_comprobantes_admin" else getattr(admin, consulta)()


def test_csv_protege_domicilio_y_conserva_importe():
    import csv
    from io import StringIO
    from web.routes.admin import ExportadorCSV
    salida = StringIO()
    ExportadorCSV(salida).writerow(["  =1+1", "+543704000000", 'Casa "A", 125', -25.50])
    salida.seek(0)
    assert next(csv.reader(salida)) == ["'  =1+1", "'+543704000000", 'Casa "A", 125', "-25.5"]
