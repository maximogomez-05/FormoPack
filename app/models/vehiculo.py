"""Modelo de Vehículo (RF 3.1 / RF 3.2)."""

from __future__ import annotations

from app.utils.exceptions import ValidationError


class Vehiculo:
    """Representa un vehículo de la flota."""

    ESTADOS_VALIDOS = {"disponible", "en_ruta", "mantenimiento", "fuera_de_servicio"}

    def __init__(
        self,
        id_vehiculo: int,
        patente: str,
        capacidad_kg: float,
        estado: str = "disponible",
    ) -> None:
        self._id_vehiculo = id_vehiculo
        self._patente = patente.strip()
        self._capacidad_kg = float(capacidad_kg)
        self._estado = estado.lower()
        self.validar_datos(self._patente, self._capacidad_kg)
        if self._estado not in self.ESTADOS_VALIDOS:
            raise ValidationError(field="estado", reason=f"Estado de vehículo no válido: '{estado}'")

    @property
    def id_vehiculo(self) -> int:
        return self._id_vehiculo

    @property
    def patente(self) -> str:
        return self._patente

    @property
    def capacidad_kg(self) -> float:
        return self._capacidad_kg

    @property
    def estado(self) -> str:
        return self._estado

    @staticmethod
    def validar_datos(patente: str, capacidad_kg: float) -> None:
        """Valida patente y capacidad del vehículo."""
        patente_limpia = (patente or "").strip()
        if not patente_limpia or len(patente_limpia) < 3:
            raise ValidationError(field="patente", reason="La patente es obligatoria y debe tener al menos 3 caracteres")
        if capacidad_kg <= 0:
            raise ValidationError(field="capacidad_kg", reason="La capacidad debe ser mayor a cero")

    def esta_disponible(self) -> bool:
        return self._estado == "disponible"

    def asignar_ruta(self) -> None:
        if not self.esta_disponible():
            raise ValueError(f"El vehículo {self._patente} no está disponible")
        self._estado = "en_ruta"

    def liberar(self) -> None:
        self._estado = "disponible"

    def to_dict(self) -> dict:
        return {
            "id_vehiculo": self._id_vehiculo,
            "patente": self._patente,
            "capacidad_kg": self._capacidad_kg,
            "estado": self._estado,
            "disponible": self.esta_disponible(),
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Vehiculo":
        return cls(
            id_vehiculo=row["id_vehiculo"],
            patente=row["patente"],
            capacidad_kg=float(row.get("capacidad_kg", 0)),
            estado=row.get("estado", "disponible"),
        )

    def __repr__(self) -> str:
        return f"<Vehiculo patente='{self._patente}' capacidad={self._capacidad_kg}kg estado='{self._estado}'>"
