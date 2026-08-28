"""Modelo de Localidad (Destinos con distancia para ruteo) — RF 3.3."""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class Localidad:
    """Entidad que representa una localidad de destino con su distancia en KM.

    Mapea a la tabla `localidades` del DER.
    Utilizada por el Cotizador para calcular tarifas por zona y por el
    ServicioRuteo para optimizar hojas de ruta (RF 3.3).
    """

    def __init__(
        self,
        id_localidad: int,
        nombre: str,
        distancia_km: float,
    ) -> None:
        self._id_localidad = id_localidad
        self._nombre = nombre
        self._distancia_km = distancia_km

    # --- Properties ---

    @property
    def id_localidad(self) -> int:
        return self._id_localidad

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def distancia_km(self) -> float:
        return self._distancia_km

    # --- Métodos de negocio (UML) ---

    def obtener_corredor_centro(self) -> str:
        """Clasifica la localidad en un corredor de ruta según distancia.

        Criterios:
            - Urbano: 0-50 KM
            - Periurbano: 51-150 KM
            - Interior: 151-300 KM
            - Frontera: >300 KM
        """
        if self._distancia_km <= 50:
            return "urbano"
        elif self._distancia_km <= 150:
            return "periurbano"
        elif self._distancia_km <= 300:
            return "interior"
        else:
            return "frontera"

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_localidad": self._id_localidad,
            "nombre": self._nombre,
            "distancia_km": self._distancia_km,
            "corredor": self.obtener_corredor_centro(),
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Localidad":
        """Instancia una Localidad desde una fila de base de datos."""
        return cls(
            id_localidad=row["id_localidad"],
            nombre=row["nombre"],
            distancia_km=float(row["distancia_km"]),
        )

    def __repr__(self) -> str:
        return f"<Localidad id={self._id_localidad} nombre='{self._nombre}' km={self._distancia_km}>"
