from datetime import datetime

from app.services.optimizador_rutas import OptimizadorRutas


def test_vrp_distribuye_pedidos_respetando_capacidad_y_orden():
    envios = [
        {"id_envio": 1, "nro_guia": "A", "destino_latitud": -26.20, "destino_longitud": -58.20,
         "peso_total_kg": 7, "prioridad": "normal"},
        {"id_envio": 2, "nro_guia": "B", "destino_latitud": -26.21, "destino_longitud": -58.21,
         "peso_total_kg": 7, "prioridad": "alta"},
    ]
    vehiculos = [
        {"id_vehiculo": 3, "patente": "AAA123", "capacidad_kg": 8},
        {"id_vehiculo": 4, "patente": "BBB123", "capacidad_kg": 8},
    ]

    plan = OptimizadorRutas.planificar(envios, vehiculos, datetime(2026, 11, 10, 8, 0))

    assert len(plan["rutas"]) == 2
    assert all(ruta["carga_kg"] <= ruta["vehiculo"]["capacidad_kg"] for ruta in plan["rutas"])
    assert {parada["id_envio"] for ruta in plan["rutas"] for parada in ruta["paradas"]} == {1, 2}
    assert plan["sin_asignar"] == []


def test_vrp_omite_coordenadas_faltantes_y_aplica_ventana_horaria():
    envios = [
        {"id_envio": 1, "destino_latitud": None, "destino_longitud": None, "peso_total_kg": 1},
        {"id_envio": 2, "destino_latitud": -26.20, "destino_longitud": -58.20, "peso_total_kg": 1,
         "ventana_desde": "08:30", "ventana_hasta": "10:00"},
    ]
    vehiculos = [{"id_vehiculo": 3, "patente": "AAA123", "capacidad_kg": 100}]

    plan = OptimizadorRutas.planificar(envios, vehiculos, datetime(2026, 11, 10, 8, 0))

    assert plan["sin_asignar"][0]["motivo"] == "Falta marcar el domicilio en el mapa"
    assert plan["rutas"][0]["paradas"][0]["hora_estimada_minuto"] >= 510


def test_vrp_marca_ordenes_que_exceden_capacidad_como_no_asignadas():
    envios = [{"id_envio": 1, "destino_latitud": -26.20, "destino_longitud": -58.20, "peso_total_kg": 20}]
    vehiculos = [{"id_vehiculo": 3, "patente": "AAA123", "capacidad_kg": 10}]

    plan = OptimizadorRutas.planificar(envios, vehiculos, datetime(2026, 11, 10, 8, 0))

    assert plan["rutas"] == []
    assert plan["sin_asignar"][0]["envio"]["id_envio"] == 1


def test_vrp_marca_ventana_vencida_sin_romper_el_solver():
    envios = [{"id_envio": 1, "destino_latitud": -26.20, "destino_longitud": -58.20,
        "peso_total_kg": 1, "ventana_desde": "08:00", "ventana_hasta": "09:00"}]
    vehiculos = [{"id_vehiculo": 3, "patente": "AAA123", "capacidad_kg": 10}]

    plan = OptimizadorRutas.planificar(envios, vehiculos, datetime(2026, 11, 10, 10, 0))

    assert plan["rutas"] == []
    assert "venció" in plan["sin_asignar"][0]["motivo"]