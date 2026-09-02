"""Servicio de ruteo para logística (RF 3.2 / RF 3.3)."""

from __future__ import annotations

from typing import Any, Iterable


class ServicioRuteo:
    """Ordena entregas por distancia y ayuda a preparar hojas de ruta."""

    @staticmethod
    def _obtener_distancia(envio: Any) -> float:
        if isinstance(envio, dict):
            return float(envio.get("distancia_km", envio.get("distancia", 0.0) or 0.0))
        if hasattr(envio, "distancia_km"):
            return float(envio.distancia_km)
        if hasattr(envio, "get"):
            return float(envio.get("distancia_km", 0.0) or 0.0)
        return 0.0

    @staticmethod
    def ordenar_envios_por_distancia(envios: Iterable[Any]) -> list[Any]:
        """Devuelve los envíos ordenados desde la ruta más corta a la más larga."""
        lista = list(envios)
        return sorted(
            lista,
            key=lambda e: (
                ServicioRuteo._obtener_distancia(e),
                str(e.get("nro_guia") if isinstance(e, dict) else getattr(e, "nro_guia", "")),
            ),
        )

    @staticmethod
    def calcular_recorrido_total(envios: Iterable[Any]) -> float:
        return sum(ServicioRuteo._obtener_distancia(e) for e in envios)
