"""Controlador para el sistema de Soporte al Cliente — Chats en vivo."""

import logging
from typing import Optional
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class SoporteController:
    """Gestiona los chats y mensajes de soporte en vivo entre clientes y operadores (admin/recepcionista)."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self._db = db_manager or DatabaseManager.get_instance()
        self.inicializar_tablas()

    def inicializar_tablas(self) -> None:
        """Crea las tablas chats_soporte y mensajes_soporte si no existen."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats_soporte (
                    id_chat INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL UNIQUE,
                    cliente_nombre VARCHAR(100) NOT NULL,
                    cliente_email VARCHAR(120) NULL,
                    nro_guia VARCHAR(30) NULL,
                    estado ENUM('sin_atender', 'en_progreso') NOT NULL DEFAULT 'sin_atender',
                    id_usuario_atendiendo INT NULL,
                    nombre_usuario_atendiendo VARCHAR(100) NULL,
                    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_soporte_estado (estado),
                    INDEX idx_soporte_usuario (id_usuario_atendiendo),
                    CONSTRAINT fk_soporte_usuario FOREIGN KEY (id_usuario_atendiendo)
                        REFERENCES usuarios(id_usuario) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mensajes_soporte (
                    id_mensaje INT AUTO_INCREMENT PRIMARY KEY,
                    id_chat INT NOT NULL,
                    remitente_tipo ENUM('cliente', 'soporte') NOT NULL,
                    remitente_nombre VARCHAR(100) NOT NULL,
                    mensaje TEXT NOT NULL,
                    fecha_envio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_msg_chat (id_chat),
                    CONSTRAINT fk_msg_chat FOREIGN KEY (id_chat)
                        REFERENCES chats_soporte(id_chat) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("Error al inicializar tablas de soporte: %s", e)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                conn.close()

    def obtener_o_crear_chat(
        self,
        session_id: str,
        cliente_nombre: str,
        nro_guia: Optional[str] = None,
        cliente_email: Optional[str] = None,
        mensaje_inicial: Optional[str] = None,
    ) -> dict:
        """Obtiene un chat existente por session_id o crea uno nuevo."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM chats_soporte WHERE session_id = %s", (session_id,))
            chat = cursor.fetchone()

            if not chat:
                cursor.execute(
                    """
                    INSERT INTO chats_soporte
                        (session_id, cliente_nombre, cliente_email, nro_guia, estado)
                    VALUES (%s, %s, %s, %s, 'sin_atender')
                    """,
                    (session_id, cliente_nombre.strip(), (cliente_email or "").strip() or None, (nro_guia or "").strip() or None),
                )
                id_chat = cursor.lastrowid
                conn.commit()

                if mensaje_inicial and mensaje_inicial.strip():
                    cursor.execute(
                        """
                        INSERT INTO mensajes_soporte
                            (id_chat, remitente_tipo, remitente_nombre, mensaje)
                        VALUES (%s, 'cliente', %s, %s)
                        """,
                        (id_chat, cliente_nombre.strip(), mensaje_inicial.strip()),
                    )
                    conn.commit()

                cursor.execute("SELECT * FROM chats_soporte WHERE id_chat = %s", (id_chat,))
                chat = cursor.fetchone()
            elif mensaje_inicial and mensaje_inicial.strip():
                # Si el chat ya existía, añadir el mensaje
                cursor.execute(
                    """
                    INSERT INTO mensajes_soporte
                        (id_chat, remitente_tipo, remitente_nombre, mensaje)
                    VALUES (%s, 'cliente', %s, %s)
                    """,
                    (chat["id_chat"], cliente_nombre.strip(), mensaje_inicial.strip()),
                )
                conn.commit()

            cursor.close()
            return chat
        finally:
            if conn:
                conn.close()

    def obtener_chat_por_id(self, id_chat: int) -> Optional[dict]:
        """Obtiene un chat por su ID primario."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM chats_soporte WHERE id_chat = %s", (id_chat,))
            chat = cursor.fetchone()
            cursor.close()
            return chat
        finally:
            if conn:
                conn.close()

    def obtener_chat_por_session(self, session_id: str) -> Optional[dict]:
        """Obtiene un chat por el token de sesión del cliente."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM chats_soporte WHERE session_id = %s", (session_id,))
            chat = cursor.fetchone()
            cursor.close()
            return chat
        finally:
            if conn:
                conn.close()

    def enviar_mensaje(
        self,
        id_chat: int,
        remitente_tipo: str,
        remitente_nombre: str,
        mensaje: str,
    ) -> Optional[dict]:
        """Agrega un mensaje al chat."""
        if not mensaje or not mensaje.strip():
            return None

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Verificar que el chat exista
            cursor.execute("SELECT * FROM chats_soporte WHERE id_chat = %s", (id_chat,))
            chat = cursor.fetchone()
            if not chat:
                cursor.close()
                return None

            cursor.execute(
                """
                INSERT INTO mensajes_soporte
                    (id_chat, remitente_tipo, remitente_nombre, mensaje)
                VALUES (%s, %s, %s, %s)
                """,
                (id_chat, remitente_tipo, remitente_nombre.strip(), mensaje.strip()),
            )
            id_mensaje = cursor.lastrowid

            # Actualizar timestamp de fecha_actualizacion
            cursor.execute("UPDATE chats_soporte SET fecha_actualizacion = NOW() WHERE id_chat = %s", (id_chat,))
            conn.commit()

            cursor.execute("SELECT * FROM mensajes_soporte WHERE id_mensaje = %s", (id_mensaje,))
            nuevo_msg = cursor.fetchone()
            cursor.close()
            return nuevo_msg
        finally:
            if conn:
                conn.close()

    def obtener_mensajes(self, id_chat: int) -> list[dict]:
        """Devuelve los mensajes de un chat ordenados cronológicamente."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id_mensaje, id_chat, remitente_tipo, remitente_nombre, mensaje, fecha_envio
                FROM mensajes_soporte
                WHERE id_chat = %s
                ORDER BY fecha_envio ASC, id_mensaje ASC
                """,
                (id_chat,),
            )
            mensajes = cursor.fetchall()
            cursor.close()
            return mensajes
        finally:
            if conn:
                conn.close()

    def listar_chats(self) -> dict:
        """Devuelve chats separados en 'sin_atender' y 'en_progreso'.

        Cada chat incluye cantidad de mensajes y el extracto del último mensaje.
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            sql = """
                SELECT 
                    c.id_chat,
                    c.session_id,
                    c.cliente_nombre,
                    c.cliente_email,
                    c.nro_guia,
                    c.estado,
                    c.id_usuario_atendiendo,
                    c.nombre_usuario_atendiendo,
                    c.fecha_creacion,
                    c.fecha_actualizacion,
                    COUNT(m.id_mensaje) AS total_mensajes,
                    (SELECT mensaje FROM mensajes_soporte WHERE id_chat = c.id_chat ORDER BY id_mensaje DESC LIMIT 1) AS ultimo_mensaje,
                    (SELECT fecha_envio FROM mensajes_soporte WHERE id_chat = c.id_chat ORDER BY id_mensaje DESC LIMIT 1) AS fecha_ultimo_mensaje
                FROM chats_soporte c
                LEFT JOIN mensajes_soporte m ON c.id_chat = m.id_chat
                GROUP BY c.id_chat
                ORDER BY c.fecha_actualizacion DESC
            """
            cursor.execute(sql)
            todos = cursor.fetchall()
            cursor.close()

            sin_atender = [c for c in todos if c["estado"] == "sin_atender"]
            en_progreso = [c for c in todos if c["estado"] == "en_progreso"]

            return {
                "sin_atender": sin_atender,
                "en_progreso": en_progreso,
                "total": len(todos),
            }
        finally:
            if conn:
                conn.close()

    def agente_tiene_chat_en_progreso(self, id_usuario: int) -> Optional[dict]:
        """Retorna el chat activo si el usuario ya está atendiendo una conversación."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT * FROM chats_soporte
                WHERE id_usuario_atendiendo = %s AND estado = 'en_progreso'
                LIMIT 1
                """,
                (id_usuario,),
            )
            chat = cursor.fetchone()
            cursor.close()
            return chat
        finally:
            if conn:
                conn.close()

    def tomar_chat(self, id_chat: int, id_usuario: int, nombre_usuario: str) -> tuple[bool, str]:
        """Asigna un chat al operador si cumple las reglas de negocio:

        1. Un solo usuario puede hablar con un chat de cliente a la vez.
        2. El operador no puede atender más de un chat al mismo tiempo.
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Verificar si el operador ya tiene OTRO chat en progreso
            cursor.execute(
                """
                SELECT id_chat, cliente_nombre FROM chats_soporte
                WHERE id_usuario_atendiendo = %s AND estado = 'en_progreso' AND id_chat != %s
                LIMIT 1
                """,
                (id_usuario, id_chat),
            )
            chat_ocupado = cursor.fetchone()
            if chat_ocupado:
                cursor.close()
                return False, f"Ya estás atendiendo la conversación #{chat_ocupado['id_chat']} con {chat_ocupado['cliente_nombre']}. Debés finalizarla antes de tomar otro chat."

            # Verificar el estado actual del chat solicitado
            cursor.execute("SELECT * FROM chats_soporte WHERE id_chat = %s", (id_chat,))
            chat = cursor.fetchone()
            if not chat:
                cursor.close()
                return False, "El chat no existe o ya ha sido finalizado."

            if chat["estado"] == "en_progreso" and chat["id_usuario_atendiendo"] not in (None, id_usuario):
                cursor.close()
                return False, f"Este chat ya está siendo atendido por {chat['nombre_usuario_atendiendo']}."

            # Asignar el chat al operador
            cursor.execute(
                """
                UPDATE chats_soporte
                SET estado = 'en_progreso',
                    id_usuario_atendiendo = %s,
                    nombre_usuario_atendiendo = %s,
                    fecha_actualizacion = NOW()
                WHERE id_chat = %s
                """,
                (id_usuario, nombre_usuario.strip(), id_chat),
            )

            # Mensaje automático de bienvenida al tomar el chat si no hay mensaje previo del soporte
            cursor.execute(
                """
                SELECT COUNT(*) AS c FROM mensajes_soporte
                WHERE id_chat = %s AND remitente_tipo = 'soporte'
                """,
                (id_chat,),
            )
            cuenta_soporte = cursor.fetchone()["c"]
            if cuenta_soporte == 0:
                cursor.execute(
                    """
                    INSERT INTO mensajes_soporte
                        (id_chat, remitente_tipo, remitente_nombre, mensaje)
                    VALUES (%s, 'soporte', %s, %s)
                    """,
                    (
                        id_chat,
                        nombre_usuario.strip(),
                        f"¡Hola! Mi nombre es {nombre_usuario} del equipo de soporte FormoPack. ¿En qué puedo ayudarte?",
                    ),
                )

            conn.commit()
            cursor.close()
            return True, "Chat asignado exitosamente."
        finally:
            if conn:
                conn.close()

    def finalizar_chat(self, id_chat: int) -> bool:
        """Termina y ELIMINA completamente la conversación y sus mensajes de la BD.

        Así no ocupa más espacio y solo quedan chats en progreso y sin atender.
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()

            # Por la clave foránea ON DELETE CASCADE, esto borra los mensajes_soporte automáticamente
            cursor.execute("DELETE FROM chats_soporte WHERE id_chat = %s", (id_chat,))
            conn.commit()
            eliminado = cursor.rowcount > 0
            cursor.close()
            return eliminado
        except Exception as e:
            logger.error("Error al finalizar chat %s: %s", id_chat, e)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if conn:
                conn.close()
