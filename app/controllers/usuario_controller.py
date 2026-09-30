import logging
import bcrypt
from app.core.database import DatabaseManager
from app.utils.exceptions import ValidationError, DuplicateError, DatabaseQueryError

logger = logging.getLogger(__name__)

class UsuarioController:
    def listar_usuarios(self) -> list[dict]:
        conn = None
        try:
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id_usuario, nombre, email, tipo_usuario, activo
                FROM usuarios
                ORDER BY tipo_usuario, nombre
            """)
            return cursor.fetchall()
        except Exception as e:
            logger.error("Error al listar usuarios: %s", e)
            raise DatabaseQueryError(f"Error al listar usuarios: {e}")
        finally:
            if conn:
                conn.close()

    def crear_usuario(self, nombre: str, email: str, tipo_usuario: str, password: str):
        if not nombre or not nombre.strip():
            raise ValidationError(field="nombre", reason="No puede estar vacío")
        if not email or "@" not in email or "." not in email:
            raise ValidationError(field="email", reason="Formato inválido")
        if tipo_usuario not in ('administrador', 'recepcionista', 'chofer'):
            raise ValidationError(field="tipo_usuario", reason="Tipo inválido")
        if not password or len(password) < 8:
            raise ValidationError(field="password", reason="Mínimo 8 caracteres")

        conn = None
        try:
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT id_usuario FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                raise DuplicateError(entity="Usuario", identifier=email)

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            cursor.execute("""
                INSERT INTO usuarios (nombre, email, tipo_usuario, credenciales_hash, activo)
                VALUES (%s, %s, %s, %s, 1)
            """, (nombre.strip(), email.strip(), tipo_usuario, hashed_password))
            conn.commit()
        except (DuplicateError, ValidationError):
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Error al crear usuario: %s", e)
            raise DatabaseQueryError(f"Error al crear usuario: {e}")
        finally:
            if conn:
                conn.close()

    def toggle_activo(self, id_usuario: int, id_solicitante: int) -> bool:
        if id_usuario == id_solicitante:
            raise ValidationError(field="id_usuario", reason="No puede desactivarse a sí mismo")

        conn = None
        try:
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT activo FROM usuarios WHERE id_usuario = %s", (id_usuario,))
            user = cursor.fetchone()
            if not user:
                raise ValidationError(field="id_usuario", reason="Usuario no encontrado")

            nuevo_estado = not user['activo']
            cursor.execute("UPDATE usuarios SET activo = %s WHERE id_usuario = %s", (int(nuevo_estado), id_usuario))
            conn.commit()
            return nuevo_estado
        except (ValidationError, DuplicateError):
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Error al toggle_activo usuario: %s", e)
            raise DatabaseQueryError(f"Error al cambiar estado: {e}")
        finally:
            if conn:
                conn.close()
