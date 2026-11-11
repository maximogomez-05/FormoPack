from datetime import datetime
from unittest.mock import MagicMock, patch

from app.controllers.chofer_controller import ChoferController
from web.app import create_app


def test_tracking_estado_publico_devuelve_solo_estado_y_gps():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"id_envio": 23, "estado_actual": "en_ruta", "id_hoja_ruta": 7},
        {
            "latitud": -26.18,
            "longitud": -58.17,
            "precision_m": 8.5,
            "fecha_actualizacion": datetime(2026, 11, 5, 12, 0),
        },
    ]
    cursor.fetchall.return_value = [
        {"id": 1, "lat": -26.18, "lng": -58.17, "fecha_hora": datetime(2026, 11, 5, 11, 59)},
        {"id": 2, "lat": -26.19, "lng": -58.18, "fecha_hora": datetime(2026, 11, 5, 12, 0)},
    ]
    conexion = MagicMock()
    conexion.cursor.return_value = cursor
    base_datos = MagicMock()
    base_datos.get_connection.return_value = conexion

    with patch("web.routes.admin.DatabaseManager.get_instance", return_value=base_datos):
        respuesta = create_app().test_client().get("/admin/tracking/estado?guia=FP-123")

    assert respuesta.status_code == 200
    assert respuesta.json == {
        "ok": True,
        "estado": "en_ruta",
        "ubicacion_gps": {
            "latitud": -26.18,
            "longitud": -58.17,
            "precision_m": 8.5,
            "fecha_actualizacion": "2026-11-05T12:00:00",
        },
        "historial_gps": [
            {"lat": -26.18, "lng": -58.17, "fecha_hora": "2026-11-05T11:59:00"},
            {"lat": -26.19, "lng": -58.18, "fecha_hora": "2026-11-05T12:00:00"},
        ],
    }
    assert cursor.execute.call_count == 3
    assert "destinatario" not in respuesta.json
    cursor.close.assert_called_once()
    conexion.close.assert_called_once()


def test_tracking_estado_entregado_no_consulta_ni_expone_gps():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id_envio": 23, "estado_actual": "entregado", "id_hoja_ruta": 7}
    conexion = MagicMock()
    conexion.cursor.return_value = cursor
    base_datos = MagicMock()
    base_datos.get_connection.return_value = conexion

    with patch("web.routes.admin.DatabaseManager.get_instance", return_value=base_datos):
        respuesta = create_app().test_client().get("/admin/tracking/estado?guia=FP-123")

    assert respuesta.status_code == 200
    assert respuesta.json == {"ok": True, "estado": "entregado", "ubicacion_gps": None, "historial_gps": []}
    assert cursor.execute.call_count == 1


def test_tracking_estado_rechaza_guia_invalida_sin_consultar_bd():
    with patch("web.routes.admin.DatabaseManager.get_instance") as get_database:
        respuesta = create_app().test_client().get("/admin/tracking/estado?guia=../privado")

    assert respuesta.status_code == 400
    assert respuesta.json["ok"] is False
    get_database.assert_not_called()


def test_actualizar_ubicacion_guarda_breadcrumb_en_la_misma_transaccion():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id_hoja_ruta": 7}
    conexion = MagicMock()
    conexion.cursor.return_value = cursor
    base_datos = MagicMock()
    base_datos.get_connection.return_value = conexion

    ChoferController(base_datos).actualizar_ubicacion_ruta(3, 7, -26.18, -58.17, 8)

    llamadas = [llamada.args[0] for llamada in cursor.execute.call_args_list]
    assert any("INSERT INTO historial_gps" in sql for sql in llamadas)
    assert any("INSERT INTO ubicaciones_hojas_ruta" in sql for sql in llamadas)
    assert cursor.execute.call_args_list[-1].args[1] == (-26.18, -58.17, 7)
    conexion.commit.assert_called_once()
    conexion.rollback.assert_not_called()


def test_vista_tracking_renderiza_mapa_osrm_y_endpoint_de_actualizacion():
    envio = {
        "nro_guia": "FP-123",
        "estado_actual": "en_ruta",
        "fecha_creacion": datetime(2026, 11, 5, 12, 0),
        "cantidad_intentos": 0,
        "localidad_destino": "Clorinda",
        "remitente": "Remitente Demo",
        "destinatario": "Destinatario Demo",
    }

    with patch("web.routes.admin._obtener_timeline", return_value=(envio, [])):
        respuesta = create_app().test_client().get("/admin/tracking?guia=FP-123")

    pagina = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "/route/v1/driving/" in pagina
    assert "/admin/tracking/estado?guia=FP-123" in pagina
    assert "mapas-seguimiento.js" in pagina
    assert "new FormoPackMapas.ConsultaPeriodica(trackingStatusUrl" in pagina
