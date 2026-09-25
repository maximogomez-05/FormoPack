"""Pruebas para RF 5.1 y RF 5.2: tracking público y timeline."""

from datetime import datetime

from web.routes.admin import construir_alertas_operativas, construir_timeline, construir_resumen_tracking


def test_construir_resumen_tracking():
    """El tracking público debe resumir el estado actual y la última actualización."""
    envio = {
        "nro_guia": "FPX-2026-0003",
        "estado_actual": "en_ruta",
        "fecha_creacion": "2026-01-13 07:00:00",
    }
    historial = [
        {"estado": "recibido", "fecha_hora": "2026-01-13 07:00:00", "ubicacion": "Sucursal Origen", "observacion": "Registrado"},
        {"estado": "en_ruta", "fecha_hora": "2026-01-13 12:30:00", "ubicacion": "Ruta Norte", "observacion": "En tránsito"},
    ]

    resumen = construir_resumen_tracking(envio, historial)

    assert resumen["estado"] == "en_ruta"
    assert resumen["ultima_actualizacion"] == "2026-01-13 12:30:00"
    assert resumen["ubicacion_actual"] == "Ruta Norte"
    assert resumen["progreso"] == "en_tránsito"


def test_construir_timeline_agrega_estado_inicial_si_falta():
    """Cuando no hay historial, el timeline debe mostrar el estado actual inicial."""
    envio = {
        "nro_guia": "FPX-2026-0001",
        "estado_actual": "recibido",
        "fecha_creacion": "2026-01-10 08:00:00",
    }

    timeline = construir_timeline(envio, [])

    assert len(timeline) == 1
    assert timeline[0]["estado"] == "recibido"
    assert timeline[0]["ubicacion"] == "Sucursal Origen"
    assert timeline[0]["observacion"] == "Envío registrado en sistema."


def test_construir_timeline_ordena_eventos_cronologicamente():
    """Los movimientos deben mostrarse en orden cronológico."""
    envio = {
        "nro_guia": "FPX-2026-0002",
        "estado_actual": "entregado",
        "fecha_creacion": "2026-01-11 09:00:00",
    }
    historial = [
        {"estado": "entregado", "fecha_hora": "2026-01-12 18:00:00", "ubicacion": "Calle 10", "observacion": "Entregado"},
        {"estado": "en_ruta", "fecha_hora": "2026-01-12 14:00:00", "ubicacion": "Ruta", "observacion": "En tránsito"},
    ]

    timeline = construir_timeline(envio, historial)

    assert [item["estado"] for item in timeline] == ["en_ruta", "entregado"]
    assert timeline[-1]["estado"] == "entregado"


def test_construir_alertas_operativas_detecta_fallidos_y_demorados():
    """RF 5.5 debe alertar entregas fallidas y envíos demorados."""
    envios = [
        {"nro_guia": "FALL-1", "estado_actual": "fallido", "fecha_creacion": "2026-01-10 08:00:00"},
        {"nro_guia": "DEM-1", "estado_actual": "recibido", "fecha_creacion": "2026-01-10 08:00:00"},
    ]

    alertas = construir_alertas_operativas(envios, datetime(2026, 1, 12, 8, 0, 0))

    assert [alerta["guia"] for alerta in alertas] == ["FALL-1", "DEM-1"]
    assert alertas[0]["tipo"] == "danger"
    assert alertas[1]["tipo"] == "warning"
