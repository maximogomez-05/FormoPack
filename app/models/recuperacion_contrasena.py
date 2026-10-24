"""Reglas del código OTP del personal (RF 1.3)."""

import re
import secrets
from datetime import datetime, timedelta

from app.utils.exceptions import ValidationError


class RecuperacionContrasena:
    """Código de seis dígitos, válido durante quince minutos y de un solo uso.

    La hora se recibe desde la base de datos para que el vencimiento no dependa
    de diferencias de zona horaria entre el servidor web y MySQL.
    """

    VIGENCIA = timedelta(minutes=15)
    MAX_INTENTOS = 5
    ERROR_CODIGO = "El código no es válido o ha expirado. Solicitá uno nuevo"

    def __init__(self, codigo_hash: str, expira_en: datetime, utilizado: bool = False,
                 intentos_fallidos: int = 0):
        self._codigo_hash = codigo_hash
        self._expira_en = expira_en
        self._utilizado = utilizado
        self._intentos_fallidos = intentos_fallidos

    @property
    def codigo_hash(self) -> str:
        return self._codigo_hash

    @property
    def intentos_fallidos(self) -> int:
        return self._intentos_fallidos

    @property
    def expira_en(self) -> datetime:
        return self._expira_en

    @property
    def utilizado(self) -> bool:
        return self._utilizado

    @classmethod
    def generar_codigo(cls) -> str:
        """El secreto se entrega solo al servicio de correo, nunca se persiste."""
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def validar_formato(codigo: str) -> None:
        if not re.fullmatch(r"[0-9]{6}", codigo):
            raise ValidationError(field="codigo", reason=RecuperacionContrasena.ERROR_CODIGO)

    def validar_codigo(self, coincide: bool, ahora: datetime) -> bool:
        if self._utilizado or ahora >= self._expira_en or self._intentos_fallidos >= self.MAX_INTENTOS:
            raise ValidationError(field="codigo", reason=self.ERROR_CODIGO)
        if not coincide:
            self._intentos_fallidos += 1
            if self._intentos_fallidos >= self.MAX_INTENTOS:
                self._utilizado = True
            raise ValidationError(field="codigo", reason=self.ERROR_CODIGO)
        return True

    def marcar_utilizado(self) -> None:
        if self._utilizado:
            raise ValidationError(field="codigo", reason=self.ERROR_CODIGO)
        self._utilizado = True
