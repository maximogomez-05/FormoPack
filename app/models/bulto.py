"""Modelo de Bulto (Paquete individual dentro de un envío) — RF 2.2 / RF 2.3."""

from __future__ import annotations
import logging
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class Bulto:
    """Entidad que representa un paquete individual dentro de un envío.

    Mapea a la tabla `bultos` del DER.
    Cada envío puede tener 1 o más bultos. El cálculo de aforo compara
    el peso real con el peso volumétrico y toma el mayor (RF 2.2).
    """

    def __init__(
        self,
        id_bulto: int,
        id_envio: int,
        peso_real: float,
        peso_volumetrico: float,
        es_fragil: bool = False,
    ) -> None:
        self._id_bulto = id_bulto
        self._id_envio = id_envio
        self._peso_real = V.decimal(peso_real, "peso_real", 0.01, V.MAX_PESO)
        self._peso_volumetrico = V.decimal(peso_volumetrico, "peso_volumetrico", 0, V.MAX_PESO)
        if not isinstance(es_fragil, bool):
            raise ValidationError("es_fragil", "La fragilidad debe ser verdadera o falsa")
        self._es_fragil = es_fragil

    @classmethod
    def validar_lista(cls, datos):
        if not isinstance(datos, list) or not 1 <= len(datos) <= 100:
            raise ValidationError("bultos", "Ingresá entre 1 y 100 bultos por envío")
        resultado = []
        for dato in datos:
            if not isinstance(dato, dict) or set(dato) - {"peso_real", "peso_volumetrico", "es_fragil"}:
                raise ValidationError("bultos", "Revisá los datos de cada bulto")
            bulto = cls(0, 0, dato.get("peso_real"), dato.get("peso_volumetrico", 0), dato.get("es_fragil", False))
            resultado.append({"peso_real": bulto.peso_real, "peso_volumetrico": bulto.peso_volumetrico, "es_fragil": bulto.es_fragil})
        return resultado

    # --- Properties ---

    @property
    def id_bulto(self) -> int:
        return self._id_bulto

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def peso_real(self) -> float:
        return self._peso_real

    @property
    def peso_volumetrico(self) -> float:
        return self._peso_volumetrico

    @property
    def es_fragil(self) -> bool:
        return self._es_fragil

    # --- Métodos de negocio (UML) ---

    def calcular_aforo(self) -> float:
        """Calcula el peso de aforo: el mayor entre peso real y volumétrico.

        El aforo es la base para el cálculo de tarifa. En logística,
        se cobra siempre por el peso que resulte mayor.

        Returns:
            Peso de aforo (máximo entre real y volumétrico).
        """
        return max(self._peso_real, self._peso_volumetrico)

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_bulto": self._id_bulto,
            "id_envio": self._id_envio,
            "peso_real": self._peso_real,
            "peso_volumetrico": self._peso_volumetrico,
            "es_fragil": self._es_fragil,
            "peso_aforo": self.calcular_aforo(),
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Bulto":
        """Instancia un Bulto desde una fila de base de datos."""
        return cls(
            id_bulto=row["id_bulto"],
            id_envio=row["id_envio"],
            peso_real=float(row["peso_real"]),
            peso_volumetrico=float(row["peso_volumetrico"]),
            es_fragil=bool(row.get("es_fragil", False)),
        )

    def __repr__(self) -> str:
        return (
            f"<Bulto id={self._id_bulto} envio={self._id_envio} "
            f"real={self._peso_real}kg vol={self._peso_volumetrico}kg "
            f"fragil={self._es_fragil}>"
        )
