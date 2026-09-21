"""Pruebas para RF 5.1 y RF 5.2: tracking público y timeline."""

from web.routes.admin import construir_timeline


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
