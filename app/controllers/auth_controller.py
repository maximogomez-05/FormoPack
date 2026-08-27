"""Controlador de autenticación y permisos (RF 1.1 / RF 1.2)."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from app.utils.exceptions import (
    AuthenticationError,
    DatabaseQueryError,
    UserInactiveError,
    UserNotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginResult:
    """Resultado del proceso de login."""
    success: bool
    usuario: Optional[Usuario] = field(default=None, compare=False)
    mensaje: str = ""
    rol: str = ""


class AuthController:
    """Controlador para autenticación y validación de roles."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self._db = db_manager or DatabaseManager.get_instance()

    def login(self, email: str, password_plano: str) -> LoginResult:
        """Autentica usuario por email y contraseña."""
        self._validar_campos_login(email, password_plano)

        fila = self._buscar_usuario_por_email(email)
        if fila is None:
            raise UserNotFoundError(identifier=email)

        usuario: Usuario = Usuario.from_db_row(fila)

        if not usuario.verificar_password(password_plano):
            raise AuthenticationError("Email o contrasena incorrectos.")

        if not usuario.activo:
            raise UserInactiveError(email=email)

        logger.info("Login exitoso: %s (%s)", usuario.email, usuario.tipo_usuario)

        return LoginResult(
            success=True,
            usuario=usuario,
            mensaje=f"Bienvenido, {usuario.nombre}.",
            rol=usuario.tipo_usuario,
        )

    def verificar_permiso(self, usuario: Usuario, roles_permitidos: list[str]) -> bool:
        """Verifica si el usuario posee un rol permitido."""
        return usuario.tiene_permiso(roles_permitidos)

    def _validar_campos_login(self, email: str, password: str) -> None:
        """Valida que los campos no estén vacíos."""
        if not email or not email.strip():
            raise ValidationError(field="email", reason="El campo email es obligatorio.")
        if "@" not in email:
            raise ValidationError(field="email", reason="El formato del email es invalido.")
        if not password or not password.strip():
            raise ValidationError(field="password", reason="El campo password es obligatorio.")

    def _buscar_usuario_por_email(self, email: str) -> Optional[dict]:
        """Consulta usuario por email en la base de datos."""
        sql = """
            SELECT id_usuario, nombre, email, credenciales_hash, tipo_usuario, nro_licencia, activo
            FROM usuarios
            WHERE email = %s
            LIMIT 1
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (email.strip().lower(),))
            resultado = cursor.fetchone()
            cursor.close()
            return resultado
        except Exception as e:
            raise DatabaseQueryError(f"Error al consultar usuario: {e}") from e
        finally:
            if conn:
                conn.close()
