import logging
import secrets
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from app.services.servicio_notificacion import enviar_codigo_recuperacion_async
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

    def solicitar_recuperacion(self, email: str) -> tuple[dict, str]:
        """Valida que el correo coincida con el usuario registrado al crearse y genera el código de 6 dígitos."""
        email_clean = (email or "").strip().lower()
        if not email_clean or "@" not in email_clean or "." not in email_clean:
            raise ValidationError(field="email", reason="Ingresá un formato de correo electrónico válido.")

        fila = self._buscar_usuario_por_email(email_clean)
        if fila is None:
            raise ValidationError(
                field="email",
                reason="El correo electrónico ingresado no coincide con ningún usuario registrado en el sistema.",
            )

        if not fila.get("activo"):
            raise UserInactiveError(email=email_clean)

        # Generar código criptográfico de 6 dígitos
        codigo = f"{secrets.randbelow(900000) + 100000}"
        expira_en = datetime.now() + timedelta(minutes=15)

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Invalidar códigos anteriores pendientes para este usuario
            cursor.execute(
                "UPDATE recuperacion_contrasenas SET utilizado = 1 WHERE id_usuario = %s AND utilizado = 0",
                (fila["id_usuario"],),
            )

            # Insertar el nuevo código
            cursor.execute(
                """
                INSERT INTO recuperacion_contrasenas (id_usuario, codigo, expira_en, utilizado)
                VALUES (%s, %s, %s, 0)
                """,
                (fila["id_usuario"], codigo, expira_en),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Error al registrar código de recuperación para %s: %s", email_clean, e)
            raise DatabaseQueryError(f"Error al generar código de recuperación: {e}") from e
        finally:
            if conn:
                conn.close()

        # Enviar código por correo de forma desacoplada
        enviar_codigo_recuperacion_async(fila["email"], fila["nombre"], codigo)

        return fila, codigo

    def restablecer_password(
        self,
        email: str,
        codigo: str,
        nueva_password: str,
        confirmar_password: str,
    ) -> bool:
        """Verifica el código recibido por correo y actualiza la contraseña del usuario."""
        email_clean = (email or "").strip().lower()
        codigo_clean = (codigo or "").strip()

        if not email_clean or "@" not in email_clean:
            raise ValidationError(field="email", reason="Ingresá un correo electrónico válido.")

        if not codigo_clean:
            raise ValidationError(field="codigo", reason="Ingresá el código de 6 dígitos recibido en tu correo.")

        if not nueva_password:
            raise ValidationError(field="nueva_password", reason="Ingresá una nueva contraseña.")

        if nueva_password != confirmar_password:
            raise ValidationError(field="confirmar_password", reason="Las contraseñas no coinciden.")

        Usuario.validar_complejidad_password(nueva_password)

        fila = self._buscar_usuario_por_email(email_clean)
        if fila is None:
            raise ValidationError(
                field="email",
                reason="El correo electrónico ingresado no coincide con ningún usuario registrado.",
            )

        if not fila.get("activo"):
            raise UserInactiveError(email=email_clean)

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT id_recuperacion, codigo, expira_en, utilizado
                FROM recuperacion_contrasenas
                WHERE id_usuario = %s AND utilizado = 0 AND expira_en >= NOW()
                ORDER BY creado_en DESC
                LIMIT 1
                """,
                (fila["id_usuario"],),
            )
            rec = cursor.fetchone()

            if not rec:
                raise ValidationError(
                    field="codigo",
                    reason="El código de recuperación ha expirado o ya fue utilizado. Solicitá uno nuevo.",
                )

            if not secrets.compare_digest(str(rec["codigo"]), codigo_clean):
                raise ValidationError(
                    field="codigo",
                    reason="El código de recuperación ingresado es incorrecto.",
                )

            nuevo_hash = Usuario.hashear_password(nueva_password)

            cursor.execute(
                "UPDATE usuarios SET credenciales_hash = %s WHERE id_usuario = %s",
                (nuevo_hash, fila["id_usuario"]),
            )

            cursor.execute(
                "UPDATE recuperacion_contrasenas SET utilizado = 1 WHERE id_recuperacion = %s",
                (rec["id_recuperacion"],),
            )

            conn.commit()
            cursor.close()
            logger.info("Contraseña actualizada exitosamente para usuario %s (#%s)", email_clean, fila["id_usuario"])
            return True
        except (ValidationError, UserInactiveError, UserNotFoundError):
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Error al restablecer contraseña: %s", e)
            raise DatabaseQueryError(f"Error al actualizar la contraseña: {e}") from e
        finally:
            if conn:
                conn.close()
