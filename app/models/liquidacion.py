"""Modelo de Liquidación de Chofer (RF 5.6).

Representa el resumen de rendimiento de un chofer en un período determinado.
No se persiste en tabla propia: se calcula dinámicamente cruzando
hojas_de_ruta, envios e intentos_entrega.
"""

from __future__ import annotations

from datetime import date
from typing import Any


class Liquidacion:
    """Resumen de rendimiento de un chofer en un rango de fechas."""

    def __init__(
        self,
        id_chofer: int,
        nombre_chofer: str,
        fecha_desde: date,
        fecha_hasta: date,
        total_hojas: int = 0,
        total_envios: int = 0,
        entregados: int = 0,
        fallidos: int = 0,
        pendientes: int = 0,
        monto_facturado: float = 0.0,
        km_recorridos: float = 0.0,
        hojas_detalle: list[dict[str, Any]] | None = None,
    ) -> None:
        self._id_chofer = id_chofer
        self._nombre_chofer = nombre_chofer
        self._fecha_desde = fecha_desde
        self._fecha_hasta = fecha_hasta
        self._total_hojas = total_hojas
        self._total_envios = total_envios
        self._entregados = entregados
        self._fallidos = fallidos
        self._pendientes = pendientes
        self._monto_facturado = monto_facturado
        self._km_recorridos = km_recorridos
        self._hojas_detalle: list[dict[str, Any]] = list(hojas_detalle or [])

    # ── Propiedades ──────────────────────────────────

    @property
    def id_chofer(self) -> int:
        return self._id_chofer

    @property
    def nombre_chofer(self) -> str:
        return self._nombre_chofer

    @property
    def fecha_desde(self) -> date:
        return self._fecha_desde

    @property
    def fecha_hasta(self) -> date:
        return self._fecha_hasta

    @property
    def total_hojas(self) -> int:
        return self._total_hojas

    @property
    def total_envios(self) -> int:
        return self._total_envios

    @property
    def entregados(self) -> int:
        return self._entregados

    @property
    def fallidos(self) -> int:
        return self._fallidos

    @property
    def pendientes(self) -> int:
        return self._pendientes

    @property
    def monto_facturado(self) -> float:
        return self._monto_facturado

    @property
    def km_recorridos(self) -> float:
        return self._km_recorridos

    @property
    def hojas_detalle(self) -> list[dict[str, Any]]:
        return list(self._hojas_detalle)

    # ── Métodos de cálculo ───────────────────────────

    def calcular_rendimiento(self) -> float:
        """Porcentaje de entregas exitosas sobre el total asignado."""
        if self._total_envios == 0:
            return 0.0
        return round((self._entregados / self._total_envios) * 100, 1)

    def calcular_tasa_fallo(self) -> float:
        """Porcentaje de entregas fallidas sobre el total asignado."""
        if self._total_envios == 0:
            return 0.0
        return round((self._fallidos / self._total_envios) * 100, 1)

    # ── Serialización ────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_chofer": self._id_chofer,
            "nombre_chofer": self._nombre_chofer,
            "fecha_desde": self._fecha_desde.isoformat(),
            "fecha_hasta": self._fecha_hasta.isoformat(),
            "total_hojas": self._total_hojas,
            "total_envios": self._total_envios,
            "entregados": self._entregados,
            "fallidos": self._fallidos,
            "pendientes": self._pendientes,
            "monto_facturado": self._monto_facturado,
            "km_recorridos": self._km_recorridos,
            "rendimiento": self.calcular_rendimiento(),
            "tasa_fallo": self.calcular_tasa_fallo(),
            "hojas_detalle": self._hojas_detalle,
        }

    def __repr__(self) -> str:
        return (
            f"<Liquidacion chofer='{self._nombre_chofer}' "
            f"periodo={self._fecha_desde}..{self._fecha_hasta} "
            f"envios={self._total_envios} rendimiento={self.calcular_rendimiento()}%>"
        )
