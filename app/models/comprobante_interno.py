"""Modelo de Comprobante Interno (No Fiscal) — RF 2.7."""

from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ComprobanteInterno:
    """Entidad que representa un comprobante de control interno (NO fiscal).

    Mapea a la tabla `comprobantes_internos` del DER.
    Genera un documento PDF de recepción o entrega para control administrativo.
    """

    def __init__(
        self,
        id_comprobante: int,
        id_envio: int,
        nro_comprobante: str,
        tipo_comprobante: str = "recepcion",
        fecha_emision: Optional[datetime] = None,
    ) -> None:
        self._id_comprobante = id_comprobante
        self._id_envio = id_envio
        self._nro_comprobante = nro_comprobante
        self._tipo_comprobante = tipo_comprobante
        self._fecha_emision = fecha_emision or datetime.now()

    # --- Properties ---

    @property
    def id_comprobante(self) -> int:
        return self._id_comprobante

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def nro_comprobante(self) -> str:
        return self._nro_comprobante

    @property
    def tipo_comprobante(self) -> str:
        return self._tipo_comprobante

    @property
    def fecha_emision(self) -> datetime:
        return self._fecha_emision

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_comprobante": self._id_comprobante,
            "id_envio": self._id_envio,
            "nro_comprobante": self._nro_comprobante,
            "tipo_comprobante": self._tipo_comprobante,
            "fecha_emision": self._fecha_emision.isoformat() if self._fecha_emision else None,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "ComprobanteInterno":
        """Instancia un ComprobanteInterno desde una fila de base de datos."""
        return cls(
            id_comprobante=row["id_comprobante"],
            id_envio=row["id_envio"],
            nro_comprobante=row["nro_comprobante"],
            tipo_comprobante=row.get("tipo_comprobante", "recepcion"),
            fecha_emision=row.get("fecha_emision"),
        )

    def __repr__(self) -> str:
        return (
            f"<ComprobanteInterno id={self._id_comprobante} "
            f"nro='{self._nro_comprobante}' tipo='{self._tipo_comprobante}'>"
        )
