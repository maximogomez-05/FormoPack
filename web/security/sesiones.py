"""Sesiones del personal verificadas contra el estado vigente de la cuenta."""

from flask import current_app, session

from app.core.database import DatabaseManager
from app.utils.exceptions import DatabaseQueryError
from config.settings import RoleConfig


class ControlSesion:
    """Una versión persistente revoca sesiones en todos los procesos web."""

    def __init__(self, db_manager=None):
        self._db = db_manager or DatabaseManager.get_instance()

    def validar(self) -> bool:
        if "usuario_id" not in session:
            return False
        conn = self._db.get_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT nombre, email, tipo_usuario, activo, version_sesion
                   FROM usuarios WHERE id_usuario = %s""", (session["usuario_id"],),
            )
            usuario = cursor.fetchone()
            if (
                not usuario or not usuario["activo"]
                or usuario["tipo_usuario"] not in RoleConfig.TODOS
                or session.get("version_sesion") != usuario["version_sesion"]
            ):
                session.clear()
                return False
            session.update(nombre=usuario["nombre"], email=usuario["email"], rol=usuario["tipo_usuario"])
            return True
        except Exception as exc:
            raise DatabaseQueryError("No se pudo verificar la sesión") from exc
        finally:
            if cursor:
                cursor.close()
            conn.close()

    @staticmethod
    def iniciar(usuario) -> None:
        session.clear()
        session.update(
            usuario_id=usuario.id_usuario, nombre=usuario.nombre, email=usuario.email,
            rol=usuario.tipo_usuario, version_sesion=usuario.version_sesion,
        )
        # Flask-Session regenera solo si el contenido de la sesión no está vacío.
        current_app.session_interface.regenerate(session)
