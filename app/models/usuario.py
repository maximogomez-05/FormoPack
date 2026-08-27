"""Modelo de Usuario y subclases por rol."""

from __future__ import annotations
import logging
from typing import Optional
import bcrypt

from config.settings import AppConfig, RoleConfig
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class Usuario:
    """Entidad base de usuario del sistema."""

    def __init__(
        self,
        id_usuario: int,
        nombre: str,
        email: str,
        credenciales_hash: str,
        tipo_usuario: str,
        activo: bool = True,
        nro_licencia: Optional[str] = None,
    ) -> None:
        self._id_usuario = id_usuario
        self._nombre = nombre
        self._email = email
        self._credenciales_hash = credenciales_hash
        self._tipo_usuario = tipo_usuario
        self._activo = activo
        self._nro_licencia = nro_licencia

    @property
    def id_usuario(self) -> int:
        return self._id_usuario

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def email(self) -> str:
        return self._email

    @property
    def tipo_usuario(self) -> str:
        return self._tipo_usuario

    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def nro_licencia(self) -> Optional[str]:
        return self._nro_licencia

    def verificar_password(self, password_plano: str) -> bool:
        """Verifica la contraseña contra el hash Bcrypt."""
        try:
            return bcrypt.checkpw(
                password_plano.encode("utf-8"),
                self._credenciales_hash.encode("utf-8"),
            )
        except Exception:
            return False

    def tiene_permiso(self, roles_permitidos: list[str]) -> bool:
        """Verifica si el rol del usuario está autorizado."""
        return self._tipo_usuario in roles_permitidos

    def to_dict(self) -> dict:
        """Serializa a diccionario excluyendo el hash."""
        return {
            "id_usuario": self._id_usuario,
            "nombre": self._nombre,
            "email": self._email,
            "tipo_usuario": self._tipo_usuario,
            "activo": self._activo,
            "nro_licencia": self._nro_licencia,
        }

    def __repr__(self) -> str:
        return f"<Usuario id={self._id_usuario} email='{self._email}' rol='{self._tipo_usuario}'>"

    @classmethod
    def from_db_row(cls, row: dict) -> "Usuario":
        """Instancia la subclase correspondiente según tipo_usuario."""
        tipo = row.get("tipo_usuario", "").lower()
        kwargs = dict(
            id_usuario=row["id_usuario"],
            nombre=row["nombre"],
            email=row["email"],
            credenciales_hash=row["credenciales_hash"],
            tipo_usuario=tipo,
            activo=bool(row.get("activo", True)),
            nro_licencia=row.get("nro_licencia"),
        )

        if tipo == RoleConfig.ADMINISTRADOR:
            return Administrador(**kwargs)
        elif tipo == RoleConfig.RECEPCIONISTA:
            return Recepcionista(**kwargs)
        elif tipo == RoleConfig.CHOFER:
            return Chofer(**kwargs)
        else:
            raise ValidationError(field="tipo_usuario", reason=f"Rol no válido: '{tipo}'")

    @staticmethod
    def hashear_password(password_plano: str) -> str:
        """Genera hash Bcrypt para almacenar."""
        salt = bcrypt.gensalt(rounds=AppConfig.BCRYPT_ROUNDS)
        return bcrypt.hashpw(password_plano.encode("utf-8"), salt).decode("utf-8")


# --- Subclases por Rol ---

class Administrador(Usuario):
    """Rol con acceso total al sistema."""

    def autorizarExcedente(self) -> None:
        """Autoriza excedentes sobre límites estándar."""
        pass

    def configurarSeguro(self) -> None:
        """Configura coberturas y porcentajes de seguro."""
        pass

    def __repr__(self) -> str:
        return f"<Administrador id={self._id_usuario} email='{self._email}'>"


class Recepcionista(Usuario):
    """Rol de mostrador y caja."""

    def __repr__(self) -> str:
        return f"<Recepcionista id={self._id_usuario} email='{self._email}'>"


class Chofer(Usuario):
    """Rol de entregas en campo."""

    def __init__(self, nro_licencia: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._nro_licencia = nro_licencia

    def __repr__(self) -> str:
        return f"<Chofer id={self._id_usuario} email='{self._email}' licencia='{self._nro_licencia}'>"
