"""Centros geográficos de las localidades atendidas por FormoPack."""

from __future__ import annotations

import math
import unicodedata


CENTROS_LOCALIDAD = {
    "Formosa Capital": (-26.1848, -58.1731),
    "Clorinda": (-25.2848, -57.7185),
    "Pirané": (-25.7324, -59.1088),
    "El Colorado": (-26.3050, -59.3729),
    "Laguna Blanca": (-25.1264, -58.2464),
    "Ibarreta": (-25.2146, -59.8587),
    "Las Lomitas": (-24.7062, -60.5930),
    "Ingeniero Juárez": (-23.8967, -61.8530),
    "Herradura": (-26.4851, -58.3117),
    "Villa Dos Trece": (-26.1930, -59.2280),
    "General Belgrano": (-24.9260, -59.0290),
    "Comandante Fontana": (-25.3340, -59.6830),
    "Estanislao del Campo": (-25.0550, -60.0930),
    "Misión Laishí": (-26.2333, -58.6000),
    "San Martín Dos": (-24.7000, -59.6830),
}

RADIO_GEOFENCE_METROS = 25_000


def normalizar_nombre(valor: str) -> str:
    texto = unicodedata.normalize("NFD", str(valor or ""))
    return " ".join("".join(c for c in texto if unicodedata.category(c) != "Mn").lower().split())


def centro_localidad(nombre: str) -> tuple[float, float] | None:
    buscado = normalizar_nombre(nombre)
    for localidad, centro in CENTROS_LOCALIDAD.items():
        if normalizar_nombre(localidad) == buscado:
            return centro
    if buscado == "formosa":
        return CENTROS_LOCALIDAD["Formosa Capital"]
    return None


def distancia_metros(origen: tuple[float, float], destino: tuple[float, float]) -> float:
    radianes = lambda valor: math.radians(valor)
    lat_a, lng_a = origen
    lat_b, lng_b = destino
    delta_lat = radianes(lat_b - lat_a)
    delta_lng = radianes(lng_b - lng_a)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(radianes(lat_a)) * math.cos(radianes(lat_b)) * math.sin(delta_lng / 2) ** 2
    return 2 * 6_371_000 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def punto_en_localidad(nombre: str, latitud: float, longitud: float, radio: float = RADIO_GEOFENCE_METROS) -> bool:
    centro = centro_localidad(nombre)
    if centro is None:
        return False
    try:
        latitud, longitud = float(latitud), float(longitud)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(latitud) or not math.isfinite(longitud) or not -90 <= latitud <= 90 or not -180 <= longitud <= 180:
        return False
    return distancia_metros(centro, (latitud, longitud)) <= radio
