"""Modelo de Seguro y valor declarado — RF 2.4."""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class Seguro:
    """Entidad que gestiona la cobertura de seguro para envíos.

    Mapea a la tabla `seguros` del DER.
    Si el valor declarado supera la cobertura estándar, se aplica un
    porcentaje adicional sobre el excedente (RF 2.4).
    """

    def __init__(
        self,
        id_seguro: int,
        cobertura_estandar: float,
        porcentaje_excedente: float,
    ) -> None:
        self._id_seguro = id_seguro
        self._cobertura_estandar = cobertura_estandar
        self._porcentaje_excedente = porcentaje_excedente

    # --- Properties ---

    @property
    def id_seguro(self) -> int:
        return self._id_seguro

    @property
    def cobertura_estandar(self) -> float:
        return self._cobertura_estandar

    @property
    def porcentaje_excedente(self) -> float:
        return self._porcentaje_excedente

    # --- Métodos de negocio (UML) ---

    def calcular_costo_cobertura(self, valor_declarado: float) -> float:
        """Calcula el costo adicional de seguro si el valor supera la cobertura estándar.

        Si valor_declarado <= cobertura_estandar → costo = 0.
        Si valor_declarado > cobertura_estandar → costo = excedente * (porcentaje / 100).

        Args:
            valor_declarado: Valor declarado del envío.

        Returns:
            Costo adicional del seguro.
        """
        if valor_declarado <= self._cobertura_estandar:
            return 0.0

        excedente = valor_declarado - self._cobertura_estandar
        costo = excedente * (self._porcentaje_excedente / 100.0)
        return round(costo, 2)

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_seguro": self._id_seguro,
            "cobertura_estandar": self._cobertura_estandar,
            "porcentaje_excedente": self._porcentaje_excedente,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Seguro":
        """Instancia un Seguro desde una fila de base de datos."""
        return cls(
            id_seguro=row["id_seguro"],
            cobertura_estandar=float(row["cobertura_estandar"]),
            porcentaje_excedente=float(row["porcentaje_excedente"]),
        )

    def __repr__(self) -> str:
        return (
            f"<Seguro id={self._id_seguro} "
            f"cobertura={self._cobertura_estandar} "
            f"excedente={self._porcentaje_excedente}%>"
        )
