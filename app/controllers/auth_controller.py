import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from app.models.recuperacion_contrasena import RecuperacionContrasena
from app.services.seguridad_recuperacion import ProtectorCodigoRecuperacion, LimiteSolicitudesRecuperacion
from config.settings import AppConfig
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
        self._protector = ProtectorCodigoRecuperacion(AppConfig.SECRET_KEY)
        self._limite_recuperacion = LimiteSolicitudesRecuperacion()

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

    def cambiar_password_inicial(self, id_usuario, version_sesion, password_actual, nueva_password, confirmacion):
        """Consume la clave provisoria y revoca las sesiones previas atómicamente."""
        if nueva_password != confirmacion:
            raise ValidationError("confirmacion", "Las contraseñas no coinciden")
        Usuario.validar_complejidad_password(nueva_password)
        conn, cursor = None, None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios WHERE id_usuario=%s FOR UPDATE", (id_usuario,))
            fila = cursor.fetchone()
            if not fila or not fila["activo"] or fila["version_sesion"] != version_sesion:
                raise AuthenticationError("La sesión ya no es válida. Volvé a iniciar sesión.")
            usuario = Usuario.from_db_row(fila)
            if not usuario.debe_cambiar_password:
                raise ValidationError("password", "La clave provisoria ya fue reemplazada")
            if not usuario.verificar_password(password_actual):
                raise ValidationError("password_actual", "La contraseña provisoria no es correcta")
            if usuario.verificar_password(nueva_password):
                raise ValidationError("nueva_password", "Elegí una contraseña diferente de la provisoria")
            nuevo_hash = Usuario.hashear_password(nueva_password)
            cursor.execute("""UPDATE usuarios SET credenciales_hash=%s, debe_cambiar_password=0,
                version_sesion=version_sesion+1 WHERE id_usuario=%s""", (nuevo_hash, id_usuario))
            cursor.execute("UPDATE recuperacion_contrasenas SET utilizado=1 WHERE id_usuario=%s AND utilizado=0", (id_usuario,))
            fila.update(credenciales_hash=nuevo_hash, debe_cambiar_password=0, version_sesion=version_sesion+1)
            conn.commit()
            return Usuario.from_db_row(fila)
        except (ValidationError, AuthenticationError):
            if conn: conn.rollback()
            raise
        except Exception as exc:
            if conn: conn.rollback()
            logger.error("No se pudo completar el primer acceso")
            raise DatabaseQueryError("No se pudo guardar la contraseña. Intentá nuevamente.") from exc
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

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
            SELECT id_usuario, nombre, email, credenciales_hash, tipo_usuario, nro_licencia, activo, version_sesion, debe_cambiar_password
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

    @staticmethod
    def _validar_email_recuperacion(email: str) -> str:
        email_clean = (email or "").strip().lower()
        if len(email_clean) > 100 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email_clean):
            raise ValidationError(field="email", reason="Ingresá un formato de correo electrónico válido")
        return email_clean

    def solicitar_recuperacion(self, email: str) -> None:
        """Emite el OTP por correo sin devolver secretos ni revelar cuentas.

        El bloqueo del usuario serializa las solicitudes y el consumo del código.
        La respuesta pública es la misma para cuentas ausentes e inactivas.
        """
        email_clean = self._validar_email_recuperacion(email)
        conn = None
        cursor = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            if not self._limite_recuperacion.admitir(cursor, self._protector.clave_cuenta(email_clean)):
                conn.commit()
                return
            cursor.execute(
                """SELECT id_usuario, nombre, email, activo FROM usuarios
                   WHERE email = %s LIMIT 1 FOR UPDATE""",
                (email_clean,),
            )
            fila = cursor.fetchone()
            if not fila or not fila["activo"]:
                conn.commit()
                return

            cursor.execute("SELECT CURRENT_TIMESTAMP AS ahora")
            ahora = cursor.fetchone()["ahora"]
            codigo = RecuperacionContrasena.generar_codigo()
            codigo_hash = self._protector.proteger(codigo, fila["id_usuario"])
            recuperacion = RecuperacionContrasena(codigo_hash, ahora + RecuperacionContrasena.VIGENCIA)
            cursor.execute(
                "UPDATE recuperacion_contrasenas SET utilizado = 1 WHERE id_usuario = %s AND utilizado = 0",
                (fila["id_usuario"],),
            )
            cursor.execute(
                """INSERT INTO recuperacion_contrasenas (id_usuario, codigo, codigo_hash, expira_en, utilizado)
                   VALUES (%s, '', %s, %s, 0)""",
                (fila["id_usuario"], recuperacion.codigo_hash, recuperacion.expira_en),
            )
            conn.commit()
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.error("No se pudo registrar la solicitud de recuperación")
            raise DatabaseQueryError("No se pudo procesar la recuperación de contraseña") from exc
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        # El código solo sale del controlador hacia el canal de correo.
        enviar_codigo_recuperacion_async(fila["email"], fila["nombre"], codigo)

    def restablecer_password(
        self,
        email: str,
        codigo: str,
        nueva_password: str,
        confirmar_password: str,
    ) -> bool:
        """Consume el OTP y cambia la clave en una única transacción."""
        email_clean = self._validar_email_recuperacion(email)
        codigo_clean = (codigo or "").strip()
        RecuperacionContrasena.validar_formato(codigo_clean)
        if nueva_password != confirmar_password:
            raise ValidationError(field="confirmar_password", reason="Las contraseñas no coinciden")
        Usuario.validar_complejidad_password(nueva_password)

        conn = None
        cursor = None
        rechazo_persistido = False
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            # Mismo orden de bloqueo que la emisión: primero usuario, luego OTP.
            cursor.execute(
                """SELECT id_usuario, activo, credenciales_hash, debe_cambiar_password FROM usuarios
                   WHERE email = %s LIMIT 1 FOR UPDATE""",
                (email_clean,),
            )
            fila = cursor.fetchone()
            if not fila or not fila["activo"]:
                raise ValidationError(field="codigo", reason=RecuperacionContrasena.ERROR_CODIGO)

            cursor.execute(
                """SELECT id_recuperacion, codigo_hash, expira_en, utilizado, intentos_fallidos,
                          CURRENT_TIMESTAMP AS ahora
                   FROM recuperacion_contrasenas
                   WHERE id_usuario = %s AND utilizado = 0
                   ORDER BY creado_en DESC, id_recuperacion DESC
                   LIMIT 1 FOR UPDATE""",
                (fila["id_usuario"],),
            )
            rec = cursor.fetchone()
            if not rec:
                raise ValidationError(field="codigo", reason=RecuperacionContrasena.ERROR_CODIGO)

            recuperacion = RecuperacionContrasena(
                rec["codigo_hash"], rec["expira_en"], bool(rec["utilizado"]), rec["intentos_fallidos"],
            )
            coincide = self._protector.verificar(codigo_clean, fila["id_usuario"], rec["codigo_hash"] or "")
            try:
                recuperacion.validar_codigo(coincide, rec["ahora"])
            except ValidationError:
                # Confirmar el intento rechazado: un rollback lo borraría del presupuesto.
                cursor.execute(
                    """UPDATE recuperacion_contrasenas SET intentos_fallidos = %s, utilizado = %s
                       WHERE id_recuperacion = %s""",
                    (recuperacion.intentos_fallidos, int(recuperacion.utilizado), rec["id_recuperacion"]),
                )
                conn.commit()
                rechazo_persistido = True
                raise
            if fila.get("debe_cambiar_password"):
                import bcrypt
                if bcrypt.checkpw(nueva_password.encode("utf-8"), fila["credenciales_hash"].encode("utf-8")):
                    raise ValidationError("nueva_password", "Elegí una contraseña diferente de la provisoria")
            nuevo_hash = Usuario.hashear_password(nueva_password)
            cursor.execute(
                "UPDATE usuarios SET credenciales_hash = %s, debe_cambiar_password = 0, version_sesion = version_sesion + 1 WHERE id_usuario = %s",
                (nuevo_hash, fila["id_usuario"]),
            )
            recuperacion.marcar_utilizado()
            cursor.execute(
                "UPDATE recuperacion_contrasenas SET utilizado = 1 WHERE id_usuario = %s AND utilizado = 0",
                (fila["id_usuario"],),
            )
            conn.commit()
            logger.info("Contraseña restablecida para usuario #%s", fila["id_usuario"])
            return True
        except ValidationError:
            if conn and not rechazo_persistido:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.error("No se pudo completar el cambio de contraseña")
            raise DatabaseQueryError("No se pudo restablecer la contraseña") from exc
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
