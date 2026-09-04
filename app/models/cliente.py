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
        import re

        dni_limpio = (dni or "").strip()
        nombre_limpio = (nombre_completo or "").strip()
        tel_limpio = (telefono or "").strip()

        # --- DNI / CUIT ---
        if not dni_limpio:
            raise ValidationError(field="dni", reason="El documento es obligatorio.")
        # Solo dígitos (DNI 7-8 dígitos, CUIT 11)
        if not re.fullmatch(r"\d{7,15}", dni_limpio):
            raise ValidationError(
                field="dni",
                reason="El documento debe contener solo dígitos (entre 7 y 15 caracteres, sin puntos ni guiones).",
            )

        # --- Nombre ---
        if not nombre_limpio:
            raise ValidationError(field="nombre_completo", reason="El nombre completo es obligatorio.")
        if len(nombre_limpio) < 3:
            raise ValidationError(field="nombre_completo", reason="El nombre debe tener al menos 3 caracteres.")
        if len(nombre_limpio) > 100:
            raise ValidationError(field="nombre_completo", reason="El nombre no puede superar 100 caracteres.")
        # Solo letras, espacios, tildes y guiones (nombres reales)
        if not re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\-'\.]+", nombre_limpio):
            raise ValidationError(
                field="nombre_completo",
                reason="El nombre solo puede contener letras, espacios y guiones.",
            )

        # --- Teléfono ---
        if not tel_limpio:
            raise ValidationError(field="telefono", reason="El teléfono de contacto es obligatorio.")
        # Permite dígitos, espacios, guiones, paréntesis y el signo +
        tel_solo_digitos = re.sub(r"[\s\-\(\)\+]", "", tel_limpio)
        if not tel_solo_digitos.isdigit():
            raise ValidationError(field="telefono", reason="El teléfono solo puede contener números.")
        if len(tel_solo_digitos) < 6 or len(tel_solo_digitos) > 15:
            raise ValidationError(
                field="telefono",
                reason="El teléfono debe tener entre 6 y 15 dígitos.",
            )

    def __repr__(self) -> str:
        return f"<Cliente id={self._id_cliente} dni='{self._dni}' nombre='{self._nombre_completo}'>"
