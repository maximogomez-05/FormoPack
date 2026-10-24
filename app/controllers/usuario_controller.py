import logging
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
        from app.services.validacion_entrada import ValidacionEntrada as V
        nombre = V.nombre(nombre)
        email = V.email(email)
        if not email:
            raise ValidationError("email", "El correo es obligatorio")
        if tipo_usuario not in ('administrador', 'recepcionista', 'chofer'):
            raise ValidationError(field="tipo_usuario", reason="Tipo inválido")
        
        from app.models.usuario import Usuario
        Usuario.validar_complejidad_password(password)

        conn = None
        try:
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT id_usuario FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                raise DuplicateError(entity="Usuario", identifier=email)

            hashed_password = Usuario.hashear_password(password)

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

            cursor.execute("SELECT activo FROM usuarios WHERE id_usuario = %s FOR UPDATE", (id_usuario,))
            user = cursor.fetchone()
            if not user:
                raise ValidationError(field="id_usuario", reason="Usuario no encontrado")

            nuevo_estado = not user['activo']
            cursor.execute(
                "UPDATE usuarios SET activo = %s, version_sesion = version_sesion + 1 WHERE id_usuario = %s",
                (int(nuevo_estado), id_usuario),
            )
            cursor.execute(
                "UPDATE recuperacion_contrasenas SET utilizado = 1 WHERE id_usuario = %s AND utilizado = 0",
                (id_usuario,),
            )
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
