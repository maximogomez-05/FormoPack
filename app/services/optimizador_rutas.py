"""Optimización de asignaciones y paradas con Vehicle Routing Problem."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, time, timedelta
from urllib.request import urlopen

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


class OptimizadorRutas:
    """Distribuye entregas entre vehículos respetando carga y ventanas horarias."""

    DEPOSITO = (
        float(os.getenv("FORMOPACK_DEPOT_LAT", "-26.18489")),
        float(os.getenv("FORMOPACK_DEPOT_LNG", "-58.17313")),
    )
    MAX_ENTREGAS = 100
    MINUTOS_SERVICIO = max(0, int(os.getenv("FORMOPACK_VRP_SERVICE_MINUTES", "10")))
    VELOCIDAD_APROXIMADA_KMH = max(1, int(os.getenv("FORMOPACK_VRP_FALLBACK_SPEED_KMH", "35")))
    PENALIDAD_PRIORIDAD = {"normal": 1_000_000, "alta": 2_000_000, "urgente": 3_000_000}

    @classmethod
    def planificar(cls, envios: list[dict], vehiculos: list[dict], ahora: datetime | None = None) -> dict:
        ahora = ahora or datetime.now()
        minuto_actual = ahora.hour * 60 + ahora.minute
        plan = {"rutas": [], "sin_asignar": [], "fuente_distancias": "geográfica aproximada"}
        disponibles = [v for v in vehiculos if float(v.get("capacidad_kg") or 0) > 0]
        if not disponibles:
            plan["sin_asignar"] = [{"envio": e, "motivo": "No hay vehículos disponibles"} for e in envios]
            return plan

        ubicados = []
        for envio in envios:
            if not cls._coordenada_valida(envio.get("destino_latitud"), envio.get("destino_longitud")):
                plan["sin_asignar"].append({"envio": envio, "motivo": "Falta marcar el domicilio en el mapa"})
            else:
                inicio = cls._minuto_hora(envio.get("ventana_desde"), minuto_actual)
                fin = cls._minuto_hora(envio.get("ventana_hasta"), 1440)
                if inicio > fin or fin < minuto_actual:
                    plan["sin_asignar"].append({"envio": envio, "motivo": "La ventana horaria ya venció o es inválida"})
                else:
                    ubicados.append(envio)

        if len(ubicados) > cls.MAX_ENTREGAS:
            plan["sin_asignar"].extend(
                {"envio": envio, "motivo": "Supera el máximo de 100 entregas por optimización"}
                for envio in ubicados[cls.MAX_ENTREGAS:]
            )
            ubicados = ubicados[:cls.MAX_ENTREGAS]
        if not ubicados:
            return plan

        puntos = [cls.DEPOSITO] + [
            (float(e["destino_latitud"]), float(e["destino_longitud"])) for e in ubicados
        ]
        tiempos, distancias, fuente = cls._matrices(puntos)
        plan["fuente_distancias"] = fuente

        manager = pywrapcp.RoutingIndexManager(len(puntos), len(disponibles), 0)
        routing = pywrapcp.RoutingModel(manager)

        def duracion_tramo(indice_origen, indice_destino):
            origen = manager.IndexToNode(indice_origen)
            destino = manager.IndexToNode(indice_destino)
            servicio = 0 if origen == 0 else cls.MINUTOS_SERVICIO
            return tiempos[origen][destino] + servicio

        callback_tiempo = routing.RegisterTransitCallback(duracion_tramo)
        routing.SetArcCostEvaluatorOfAllVehicles(callback_tiempo)
        routing.AddDimension(callback_tiempo, 1440, 1440, False, "Tiempo")
        dimension_tiempo = routing.GetDimensionOrDie("Tiempo")
        for vehiculo in range(len(disponibles)):
            dimension_tiempo.CumulVar(routing.Start(vehiculo)).SetRange(minuto_actual, minuto_actual)
            dimension_tiempo.CumulVar(routing.End(vehiculo)).SetRange(minuto_actual, 1440)

        def demanda(indice):
            nodo = manager.IndexToNode(indice)
            if nodo == 0:
                return 0
            return max(0, int(round(float(ubicados[nodo - 1].get("peso_total_kg") or 0) * 100)))

        callback_demanda = routing.RegisterUnaryTransitCallback(demanda)
        capacidades = [max(0, int(round(float(v["capacidad_kg"]) * 100))) for v in disponibles]
        routing.AddDimensionWithVehicleCapacity(callback_demanda, 0, capacidades, True, "Carga")

        for posicion, envio in enumerate(ubicados, start=1):
            indice = manager.NodeToIndex(posicion)
            inicio = cls._minuto_hora(envio.get("ventana_desde"), minuto_actual)
            fin = cls._minuto_hora(envio.get("ventana_hasta"), 1440)
            if fin < minuto_actual or inicio > fin:
                fin = inicio - 1
            dimension_tiempo.CumulVar(indice).SetRange(max(minuto_actual, inicio), fin)
            prioridad = str(envio.get("prioridad") or "normal").lower()
            penalidad = cls.PENALIDAD_PRIORIDAD.get(prioridad, cls.PENALIDAD_PRIORIDAD["normal"])
            routing.AddDisjunction([indice], penalidad)
            preferencia = {"urgente": (30, 20), "alta": (90, 8)}.get(prioridad)
            if preferencia:
                minutos_objetivo, costo_por_minuto = preferencia
                llegada_preferida = min(fin, max(minuto_actual, inicio) + minutos_objetivo)
                dimension_tiempo.SetCumulVarSoftUpperBound(indice, llegada_preferida, costo_por_minuto)

        parametros = pywrapcp.DefaultRoutingSearchParameters()
        parametros.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        parametros.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        parametros.time_limit.FromSeconds(5)
        solucion = routing.SolveWithParameters(parametros)
        if solucion is None:
            plan["sin_asignar"].extend(
                {"envio": envio, "motivo": "No hay una combinación factible de carga y horarios"}
                for envio in ubicados
            )
            return plan

        asignados = set()
        for indice_vehiculo, vehiculo in enumerate(disponibles):
            indice = routing.Start(indice_vehiculo)
            paradas = []
            distancia_total = 0
            carga_total = 0.0
            while not routing.IsEnd(indice):
                nodo = manager.IndexToNode(indice)
                siguiente = solucion.Value(routing.NextVar(indice))
                nodo_siguiente = manager.IndexToNode(siguiente)
                if nodo_siguiente != 0:
                    envio = dict(ubicados[nodo_siguiente - 1])
                    envio["orden_parada"] = len(paradas) + 1
                    envio["hora_estimada_minuto"] = solucion.Value(dimension_tiempo.CumulVar(siguiente))
                    paradas.append(envio)
                    asignados.add(envio["id_envio"])
                    carga_total += float(envio.get("peso_total_kg") or 0)
                distancia_total += distancias[nodo][nodo_siguiente]
                indice = siguiente
            if paradas:
                plan["rutas"].append({
                    "vehiculo": vehiculo,
                    "paradas": paradas,
                    "carga_kg": round(carga_total, 2),
                    "distancia_km": round(distancia_total / 1000, 1),
                })

        for envio in ubicados:
            if envio["id_envio"] not in asignados:
                plan["sin_asignar"].append({"envio": envio, "motivo": "Prioridad, capacidad u horario incompatible"})
        return plan

    @staticmethod
    def _coordenada_valida(latitud, longitud) -> bool:
        try:
            latitud, longitud = float(latitud), float(longitud)
            return math.isfinite(latitud) and math.isfinite(longitud) and -90 <= latitud <= 90 and -180 <= longitud <= 180
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _minuto_hora(valor, predeterminado: int) -> int:
        if valor in (None, ""):
            return predeterminado
        if isinstance(valor, timedelta):
            return int(valor.total_seconds() // 60)
        if isinstance(valor, (time, datetime)):
            return valor.hour * 60 + valor.minute
        partes = str(valor).split(":")
        if len(partes) < 2:
            return predeterminado
        return int(partes[0]) * 60 + int(partes[1])

    @classmethod
    def _matrices(cls, puntos: list[tuple[float, float]]) -> tuple[list[list[int]], list[list[int]], str]:
        base_url = os.getenv("FORMOPACK_OSRM_URL", "").rstrip("/")
        if base_url:
            coordenadas = ";".join(f"{lng:.7f},{lat:.7f}" for lat, lng in puntos)
            url = f"{base_url}/table/v1/driving/{coordenadas}?annotations=duration,distance"
            try:
                with urlopen(url, timeout=8) as respuesta:
                    datos = json.loads(respuesta.read().decode("utf-8"))
                if datos.get("code") == "Ok" and all(row and all(valor is not None for valor in row) for row in datos["durations"]):
                    tiempos = [[max(0, math.ceil(segundos / 60)) for segundos in fila] for fila in datos["durations"]]
                    distancias = [[max(0, round(metros)) for metros in fila] for fila in datos["distances"]]
                    return tiempos, distancias, "OSRM privado"
            except Exception:
                pass

        tiempos, distancias = [], []
        for lat_a, lng_a in puntos:
            fila_tiempo, fila_distancia = [], []
            for lat_b, lng_b in puntos:
                distancia = 2 * 6_371_000 * math.asin(math.sqrt(
                    math.sin(math.radians(lat_b - lat_a) / 2) ** 2
                    + math.cos(math.radians(lat_a)) * math.cos(math.radians(lat_b))
                    * math.sin(math.radians(lng_b - lng_a) / 2) ** 2
                ))
                distancia = round(distancia * 1.25)
                fila_distancia.append(distancia)
                fila_tiempo.append(math.ceil(distancia / (cls.VELOCIDAD_APROXIMADA_KMH * 1000) * 60))
            tiempos.append(fila_tiempo)
            distancias.append(fila_distancia)
        return tiempos, distancias, "geográfica aproximada"