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
        email: Optional[str] = None,
    ) -> None:
        self._id_cliente = id_cliente
        self._dni = dni
        self._nombre_completo = nombre_completo
        self._telefono = telefono
        self._email = email

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

    @property
    def email(self) -> Optional[str]:
        return self._email

    # --- Métodos de negocio (UML) ---

    def obtener_datos_contacto(self) -> str:
        """Retorna una cadena formateada con los datos de contacto del cliente."""
        email_str = f" | Email: {self._email}" if self._email else ""
        return f"{self._nombre_completo} | DNI: {self._dni} | Tel: {self._telefono}{email_str}"

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario para respuestas/JSON."""
        return {
            "id_cliente": self._id_cliente,
            "dni": self._dni,
            "nombre_completo": self._nombre_completo,
            "telefono": self._telefono,
            "email": self._email,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Cliente":
        """Instancia un Cliente desde una fila de base de datos."""
        return cls(
            id_cliente=row["id_cliente"],
            dni=row["dni"],
            nombre_completo=row["nombre_completo"],
            telefono=row["telefono"],
            email=row.get("email"),
        )

    @staticmethod
    def validar_datos(dni: str, nombre_completo: str, telefono: str, email: Optional[str] = None) -> None:
        """Valida los datos obligatorios y opcionales de un cliente antes del registro."""
        from app.services.validacion_entrada import ValidacionEntrada as V

        V.documento(dni)
        V.nombre(nombre_completo)
        V.telefono(telefono)
        V.email(email)

    def __repr__(self) -> str:
        return f"<Cliente id={self._id_cliente} dni='{self._dni}' nombre='{self._nombre_completo}' email='{self._email}'>"
