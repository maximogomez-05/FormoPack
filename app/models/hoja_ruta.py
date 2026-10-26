"""Modelo de Hoja de Ruta (RF 3.2 / RF 3.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.ruteo import ServicioRuteo


class HojaRuta:
    """Agrupa un conjunto de envíos asignados a un chofer y un vehículo."""

    def __init__(
        self,
        id_hoja_ruta: int,
        nro_despacho: str,
        id_chofer: int,
        id_vehiculo: int,
        fecha_emision: datetime | None = None,
        envios: list[dict[str, Any]] | None = None,
        estado: str = "abierta", fecha_inicio=None, fecha_cierre=None,
    ) -> None:
        self.estado, self.fecha_inicio, self.fecha_cierre = estado, fecha_inicio, fecha_cierre
        self._id_hoja_ruta = id_hoja_ruta
        self._nro_despacho = nro_despacho
        self._id_chofer = id_chofer
        self._id_vehiculo = id_vehiculo
        self._fecha_emision = fecha_emision or datetime.now()
        self._envios: list[dict[str, Any]] = list(envios or [])

    @property
    def id_hoja_ruta(self) -> int:
        return self._id_hoja_ruta

    @property
    def nro_despacho(self) -> str:
        return self._nro_despacho

    @property
    def id_chofer(self) -> int:
        return self._id_chofer

    @property
    def id_vehiculo(self) -> int:
        return self._id_vehiculo

    @property
    def envios(self) -> list[dict[str, Any]]:
        return list(self._envios)

    @property
    def fecha_emision(self) -> datetime:
        return self._fecha_emision

    def agregar_envio(self, envio: dict[str, Any]) -> None:
        self._envios.append(dict(envio))

    def ordenar_envios_por_distancia(self) -> list[dict[str, Any]]:
        return ServicioRuteo.ordenar_envios_por_distancia(self._envios)

    def total_km(self) -> float:
        return sum(float(ServicioRuteo._obtener_distancia(e)) for e in self._envios)

    def to_dict(self) -> dict:
        return {
            "id_hoja_ruta": self._id_hoja_ruta, "estado": self.estado,
            "fecha_inicio": self.fecha_inicio.isoformat() if self.fecha_inicio else None,
            "fecha_cierre": self.fecha_cierre.isoformat() if self.fecha_cierre else None,
            "nro_despacho": self._nro_despacho,
            "id_chofer": self._id_chofer,
            "id_vehiculo": self._id_vehiculo,
            "fecha_emision": self._fecha_emision.isoformat(),
            "total_km": self.total_km(),
            "cantidad_envios": len(self._envios),
            "envios": self.ordenar_envios_por_distancia(),
        }

    def __repr__(self) -> str:
        return f"<HojaRuta nro='{self._nro_despacho}' chofer={self._id_chofer} vehiculo={self._id_vehiculo} envios={len(self._envios)}>"
