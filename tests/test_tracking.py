"""Pruebas para RF 5.1 y RF 5.2: tracking público y timeline."""

from datetime import datetime

from web.routes.admin import construir_alertas_operativas, construir_timeline, construir_resumen_tracking


def test_construir_resumen_tracking():
    """El tracking público debe resumir el estado actual y la última actualización."""
    envio = {
        "nro_guia": "FPX-2026-0003",
        "estado_actual": "en_ruta",
        "fecha_creacion": "2026-01-13 07:00:00",
        "cantidad_intentos": 0,
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
    assert resumen["en_custodia"] is False
    assert resumen["cantidad_intentos"] == 0


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
    # Verificar que se generó descripción amigable
    assert "descripcion_amigable" in timeline[0]
    assert "recibido" in timeline[0]["descripcion_amigable"].lower() or "paquete" in timeline[0]["descripcion_amigable"].lower()


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


def test_alertas_miden_desde_ultimo_cambio_de_estado():
    """Una transición reciente no debe alertar usando la antigüedad del envío."""
    envios = [{
        "nro_guia": "RUTA-RECIENTE",
        "estado_actual": "en_ruta",
        "fecha_creacion": "2026-10-01 08:00:00",
        "fecha_estado": "2026-10-06 18:00:00",
    }]

    alertas = construir_alertas_operativas(envios, datetime(2026, 10, 7, 8, 0, 0))

    assert alertas == []


def test_alerta_fallida_incluye_intentos_y_motivo():
    """La alerta de fallo debe dar contexto para decidir reintento o devolución."""
    envios = [{
        "nro_guia": "FALL-2",
        "estado_actual": "fallido",
        "cantidad_intentos": 2,
        "motivo_fallo": "destinatario_ausente",
    }]

    alertas = construir_alertas_operativas(envios, datetime(2026, 10, 7, 8, 0, 0))

    assert len(alertas) == 1
    assert "2 intento(s)" in alertas[0]["mensaje"]
    assert "Destinatario ausente" in alertas[0]["mensaje"]


def test_resumen_tracking_detecta_custodia():
    """Cuando un envío fallido tiene ≥3 intentos, se marca como en custodia."""
    envio = {
        "nro_guia": "FPX-2026-CUST",
        "estado_actual": "fallido",
        "fecha_creacion": "2026-01-15 09:00:00",
        "cantidad_intentos": 3,
    }
    historial = [
        {"estado": "recibido", "fecha_hora": "2026-01-15 09:00:00", "ubicacion": "Sucursal Origen", "observacion": "Registrado"},
        {"estado": "fallido", "fecha_hora": "2026-01-16 14:00:00", "ubicacion": "Ruta Norte", "observacion": "destinatario_ausente"},
    ]

    resumen = construir_resumen_tracking(envio, historial)

    assert resumen["en_custodia"] is True
    assert resumen["cantidad_intentos"] == 3
    assert resumen["progreso"] == "fallido"


def test_resumen_tracking_no_custodia_con_pocos_intentos():
    """Un envío fallido con menos de 3 intentos NO es custodia."""
    envio = {
        "nro_guia": "FPX-2026-NOCUST",
        "estado_actual": "fallido",
        "fecha_creacion": "2026-01-15 09:00:00",
        "cantidad_intentos": 1,
    }
    historial = [
        {"estado": "fallido", "fecha_hora": "2026-01-16 14:00:00", "ubicacion": "Ruta Norte", "observacion": "destinatario_ausente"},
    ]

    resumen = construir_resumen_tracking(envio, historial)

    assert resumen["en_custodia"] is False
    assert resumen["cantidad_intentos"] == 1


def test_timeline_incluye_descripcion_amigable():
    """Cada evento del timeline debe tener una descripción amigable para el cliente."""
    envio = {
        "nro_guia": "FPX-2026-AMI",
        "estado_actual": "entregado",
        "fecha_creacion": "2026-02-01 08:00:00",
    }
    historial = [
        {"estado": "recibido", "fecha_hora": "2026-02-01 08:00:00", "ubicacion": "Sucursal Origen", "observacion": "Registrado"},
        {"estado": "en_ruta", "fecha_hora": "2026-02-01 12:00:00", "ubicacion": "Ruta Norte", "observacion": "Salida"},
        {"estado": "entregado", "fecha_hora": "2026-02-01 16:30:00", "ubicacion": "Calle 10", "observacion": "Entregado en mano"},
    ]

    timeline = construir_timeline(envio, historial)

    assert len(timeline) == 3
    for evento in timeline:
        assert "descripcion_amigable" in evento
        assert len(evento["descripcion_amigable"]) > 10  # Descripción significativa

    # Verificar que el evento de entrega tiene un mensaje con checkmark
    assert "✓" in timeline[-1]["descripcion_amigable"] or "entregado" in timeline[-1]["descripcion_amigable"].lower()


def test_timeline_descripcion_amigable_fallido_con_motivo():
    """El timeline debe generar explicaciones amigables para entregas fallidas con motivo conocido."""
    envio = {
        "nro_guia": "FPX-2026-FAIL",
        "estado_actual": "fallido",
        "fecha_creacion": "2026-02-01 08:00:00",
    }
    historial = [
        {"estado": "fallido", "fecha_hora": "2026-02-02 14:30:00", "ubicacion": "Barrio Norte",
         "observacion": "destinatario_ausente"},
    ]

    timeline = construir_timeline(envio, historial)

    assert len(timeline) == 1
    desc = timeline[0]["descripcion_amigable"]
    # Debe contener el mensaje amigable, no el código técnico
    assert "domicilio" in desc.lower() or "encontramos" in desc.lower()
    assert "14:30" in desc


def test_resumen_no_encontrado_incluye_campos_enriquecidos():
    """Un resumen sin envío debe incluir los nuevos campos con valores por defecto."""
    resumen = construir_resumen_tracking(None, [])

    assert resumen["estado"] == "no_encontrado"
    assert resumen["en_custodia"] is False
    assert resumen["cantidad_intentos"] == 0
