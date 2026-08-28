"""Modelo de Cliente (Remitente / Destinatario) — RF 2.1."""

from __future__ import annotations
import logging
from typing import Optional

from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class Cliente:
    """Entidad que representa un remitente o destinatario de envíos.

    Mapea a la tabla `clientes` del DER.
    Atributos obligatorios: DNI y teléfono de contacto (RF 2.1).
    """

    def __init__(
        self,
        id_cliente: int,
        dni: str,
        nombre_completo: str,
        telefono: str,
    ) -> None:
        self._id_cliente = id_cliente
        self._dni = dni
        self._nombre_completo = nombre_completo
        self._telefono = telefono

    # --- Properties ---

    @property
    def id_cliente(self) -> int:
        return self._id_cliente

    @property
    def dni(self) -> str:
        return self._dni

    @property
    def nombre_completo(self) -> str:
        return self._nombre_completo

    @property
    def telefono(self) -> str:
        return self._telefono

    # --- Métodos de negocio (UML) ---

    def obtener_datos_contacto(self) -> str:
        """Retorna una cadena formateada con los datos de contacto del cliente."""
        return f"{self._nombre_completo} | DNI: {self._dni} | Tel: {self._telefono}"

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario para respuestas/JSON."""
        return {
            "id_cliente": self._id_cliente,
            "dni": self._dni,
            "nombre_completo": self._nombre_completo,
            "telefono": self._telefono,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Cliente":
        """Instancia un Cliente desde una fila de base de datos."""
        return cls(
            id_cliente=row["id_cliente"],
            dni=row["dni"],
            nombre_completo=row["nombre_completo"],
            telefono=row["telefono"],
        )

    @staticmethod
    def validar_datos(dni: str, nombre_completo: str, telefono: str) -> None:
        """Valida los datos obligatorios de un cliente antes del registro."""
        if not dni or not dni.strip():
            raise ValidationError(field="dni", reason="El DNI es obligatorio.")
        if not nombre_completo or not nombre_completo.strip():
            raise ValidationError(field="nombre_completo", reason="El nombre es obligatorio.")
        if not telefono or not telefono.strip():
            raise ValidationError(field="telefono", reason="El telefono es obligatorio.")
        if len(dni.strip()) < 7 or len(dni.strip()) > 15:
            raise ValidationError(field="dni", reason="El DNI debe tener entre 7 y 15 caracteres.")

    def __repr__(self) -> str:
        return f"<Cliente id={self._id_cliente} dni='{self._dni}' nombre='{self._nombre_completo}'>"
