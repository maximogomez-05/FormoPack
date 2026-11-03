"""Sesiones del personal verificadas contra el estado vigente de la cuenta."""

from time import time

from flask import current_app, session, request

from app.core.database import DatabaseManager
from app.utils.exceptions import DatabaseQueryError, AuthenticationError
from config.settings import RoleConfig


class ControlSesion:
    """Una versión persistente revoca sesiones en todos los procesos web."""

    def __init__(self, db_manager=None):
        self._db = db_manager or DatabaseManager.get_instance()

    def validar(self) -> bool:
        if "usuario_id" not in session:
            return False
        ahora = time()
        inicio = session.get("inicio_sesion", 0)
        actividad = session.get("ultima_actividad", 0)
        inactividad = 8 * 3600 if session.get("rol") == "chofer" else 30 * 60
        if ahora - inicio >= 12 * 3600 or ahora - actividad >= inactividad:
            session.clear()
            return False
        conn = self._db.get_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT nombre, email, tipo_usuario, activo, version_sesion, debe_cambiar_password
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
            session["debe_cambiar_password"] = bool(usuario.get("debe_cambiar_password", False))
            # Las consultas automáticas no equivalen a actividad del operador.
            from web.security.error_handlers import ManejadorErroresSeguridad
            if request.endpoint != "auth.estado_sesion" and (
                request.method != "GET" or not ManejadorErroresSeguridad.espera_json()
            ):
                session["ultima_actividad"] = ahora
            return True
        except Exception as exc:
            raise DatabaseQueryError("No se pudo verificar la sesión") from exc
        finally:
            if cursor:
                cursor.close()
            conn.close()

    @staticmethod
    def finalizar() -> None:
        """Revoca también copias del identificador anterior al cierre."""
        with DatabaseManager.get_instance().cursor() as cursor:
            cursor.execute(
                """UPDATE usuarios SET version_sesion=version_sesion+1
                   WHERE id_usuario=%s AND version_sesion=%s""",
                (session["usuario_id"], session["version_sesion"]),
            )
        session.clear()
        # Elimina la entrada previa del almacén antes de guardar el aviso de salida.
        session["salida"] = True
        current_app.session_interface.regenerate(session)
        session.clear()

    @staticmethod
    def iniciar(usuario) -> None:
        # La comparación impide resucitar permisos si la cuenta cambió durante el login.
        with DatabaseManager.get_instance().cursor() as cursor:
            cursor.execute(
                """UPDATE usuarios SET version_sesion=version_sesion+1
                   WHERE id_usuario=%s AND version_sesion=%s AND activo=1""",
                (usuario.id_usuario, usuario.version_sesion),
            )
            if cursor.rowcount != 1:
                raise AuthenticationError("La cuenta cambió. Volvé a iniciar sesión.")
        session.clear()
        session.update(
            usuario_id=usuario.id_usuario, nombre=usuario.nombre, email=usuario.email,
            rol=usuario.tipo_usuario, version_sesion=usuario.version_sesion + 1,
            debe_cambiar_password=usuario.debe_cambiar_password,
            inicio_sesion=time(), ultima_actividad=time(),
        )
        # Flask-Session regenera solo si el contenido de la sesión no está vacío.
        current_app.session_interface.regenerate(session)
