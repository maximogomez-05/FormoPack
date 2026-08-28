"""Modelo de Historial de Estados (Timeline de tracking) — RF 5.1."""

from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HistorialEstado:
    """Entidad que registra cada cambio de estado de un envío.

    Mapea a la tabla `historial_estados` del DER.
    Cada vez que un envío cambia de estado, se genera un registro
    en esta tabla para construir el timeline de tracking (RF 5.1).
    """

    def __init__(
        self,
        id_historial: int,
        id_envio: int,
        estado: str,
        fecha_hora: Optional[datetime] = None,
        ubicacion: Optional[str] = None,
        observacion: Optional[str] = None,
    ) -> None:
        self._id_historial = id_historial
        self._id_envio = id_envio
        self._estado = estado
        self._fecha_hora = fecha_hora or datetime.now()
        self._ubicacion = ubicacion
        self._observacion = observacion

    # --- Properties ---

    @property
    def id_historial(self) -> int:
        return self._id_historial

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def fecha_hora(self) -> datetime:
        return self._fecha_hora

    @property
    def ubicacion(self) -> Optional[str]:
        return self._ubicacion

    @property
    def observacion(self) -> Optional[str]:
        return self._observacion

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario para el timeline de tracking."""
        return {
            "id_historial": self._id_historial,
            "id_envio": self._id_envio,
            "estado": self._estado,
            "fecha_hora": self._fecha_hora.isoformat() if self._fecha_hora else None,
            "ubicacion": self._ubicacion,
            "observacion": self._observacion,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "HistorialEstado":
        """Instancia un HistorialEstado desde una fila de base de datos."""
        return cls(
            id_historial=row["id_historial"],
            id_envio=row["id_envio"],
            estado=row["estado"],
            fecha_hora=row.get("fecha_hora"),
            ubicacion=row.get("ubicacion"),
            observacion=row.get("observacion"),
        )

    def __repr__(self) -> str:
        return (
            f"<HistorialEstado id={self._id_historial} envio={self._id_envio} "
            f"estado='{self._estado}' fecha='{self._fecha_hora}'>"
        )
