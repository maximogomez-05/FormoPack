"""Aplicación del chat uno a uno, con permisos y transacciones (RF 5.6)."""

import logging
import re
from contextlib import contextmanager

from app.core.database import DatabaseManager
from app.models.chat_soporte import ChatSoporte, MensajeSoporte
from app.utils.exceptions import SoporteError, DatabaseQueryError

logger = logging.getLogger(__name__)


class SoporteController:
    def __init__(self, db_manager=None):
        self._db = db_manager or DatabaseManager.get_instance()

    @contextmanager
    def _transaccion(self):
        conn, cursor = None, None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            yield cursor
            conn.commit()
        except SoporteError:
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.error("No se pudo completar una operación de soporte")
            raise DatabaseQueryError("El servicio de soporte no está disponible") from exc
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @staticmethod
    def _operador(cursor, id_usuario, bloquear=False):
        cursor.execute(
            "SELECT id_usuario, nombre, tipo_usuario, activo FROM usuarios WHERE id_usuario = %s"
            + (" FOR UPDATE" if bloquear else ""), (id_usuario,),
        )
        fila = cursor.fetchone()
        if not fila or not fila["activo"] or fila["tipo_usuario"] not in {"administrador", "recepcionista"}:
            raise SoporteError("No tenés permiso para operar el soporte.", 403, "SUPPORT_FORBIDDEN")
        return fila

    @staticmethod
    def _chat(cursor, id_chat):
        cursor.execute("SELECT * FROM chats_soporte WHERE id_chat = %s FOR UPDATE", (id_chat,))
        fila = cursor.fetchone()
        if not fila:
            raise SoporteError("La conversación no existe.", 404, "CHAT_NOT_FOUND")
        return fila

    @staticmethod
    def _mensajes(cursor, id_chat):
        cursor.execute(
            """SELECT id_mensaje, remitente_tipo, remitente_nombre, mensaje, fecha_envio
               FROM mensajes_soporte WHERE id_chat = %s ORDER BY id_mensaje""", (id_chat,),
        )
        return cursor.fetchall()

    @staticmethod
    def _insertar_mensaje(cursor, id_chat, tipo, nombre, texto):
        cursor.execute(
            """INSERT INTO mensajes_soporte (id_chat, remitente_tipo, remitente_nombre, mensaje)
               VALUES (%s, %s, %s, %s)""", (id_chat, tipo, nombre, texto),
        )
        id_mensaje = cursor.lastrowid
        cursor.execute("UPDATE chats_soporte SET fecha_actualizacion = NOW() WHERE id_chat = %s", (id_chat,))
        cursor.execute("SELECT * FROM mensajes_soporte WHERE id_mensaje = %s", (id_mensaje,))
        return cursor.fetchone()

    @staticmethod
    def _sin_token(chat):
        return {clave: valor for clave, valor in chat.items() if clave != "session_id"}

    @staticmethod
    def _texto(valor, nombre, maximo, obligatorio=False):
        if valor is None and not obligatorio:
            return None
        if not isinstance(valor, str) or len(valor.strip()) > maximo or any(ord(c) < 32 for c in valor):
            raise SoporteError(f"Revisá el campo {nombre}.")
        valor = valor.strip()
        if obligatorio and not valor:
            raise SoporteError(f"El campo {nombre} es obligatorio.")
        return valor or None

    def iniciar_chat(self, token, nombre, email=None, guia=None, mensaje=None):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
            raise SoporteError("La sesión de soporte no es válida.", 403, "SUPPORT_FORBIDDEN")
        nombre = self._texto(nombre, "nombre", 100, True)
        email = self._texto(email, "correo", 120)
        guia = self._texto(guia, "guía", 30)
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise SoporteError("Ingresá un correo electrónico válido.")
        texto = MensajeSoporte(mensaje).texto if mensaje is not None else None
        with self._transaccion() as cur:
            # El upsert toma bloqueo exclusivo incluso para solicitudes repetidas.
            cur.execute(
                """INSERT INTO chats_soporte (session_id, cliente_nombre, cliente_email, nro_guia)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE id_chat = LAST_INSERT_ID(id_chat)""",
                (token, nombre, email, guia),
            )
            cur.execute("SELECT * FROM chats_soporte WHERE session_id = %s FOR UPDATE", (token,))
            chat = cur.fetchone()
            if ChatSoporte(chat).cerrado:
                raise SoporteError("La conversación ya fue finalizada.", 409, "CHAT_CLOSED")
            cur.execute("SELECT COUNT(*) AS total FROM mensajes_soporte WHERE id_chat = %s", (chat["id_chat"],))
            cantidad_mensajes = cur.fetchone()["total"]
            if texto and cantidad_mensajes == 0:
                self._insertar_mensaje(cur, chat["id_chat"], "cliente", chat["cliente_nombre"], texto)
            return self._sin_token(chat)

    def consultar_cliente(self, token):
        if not token:
            return None, []
        with self._transaccion() as cur:
            cur.execute("SELECT * FROM chats_soporte WHERE session_id = %s FOR UPDATE", (token,))
            chat = cur.fetchone()
            if not chat:
                return None, []
            mensajes = [] if ChatSoporte(chat).cerrado else self._mensajes(cur, chat["id_chat"])
            return self._sin_token(chat), mensajes

    def enviar_cliente(self, token, texto):
        mensaje = MensajeSoporte(texto)
        with self._transaccion() as cur:
            cur.execute("SELECT * FROM chats_soporte WHERE session_id = %s FOR UPDATE", (token,))
            chat = cur.fetchone()
            if not chat or ChatSoporte(chat).cerrado:
                raise SoporteError("La conversación ya fue finalizada.", 409, "CHAT_CLOSED")
            return self._insertar_mensaje(cur, chat["id_chat"], "cliente", chat["cliente_nombre"], mensaje.texto)

    def consultar_staff(self, id_chat, id_usuario):
        with self._transaccion() as cur:
            operador = self._operador(cur, id_usuario)
            chat = self._chat(cur, id_chat)
            politica = ChatSoporte(chat)
            politica.validar_lectura(id_usuario, operador["tipo_usuario"])
            mensajes = [] if politica.cerrado else self._mensajes(cur, id_chat)
            return self._sin_token(chat), mensajes

    def listar_chats(self, id_usuario):
        with self._transaccion() as cur:
            operador = self._operador(cur, id_usuario)
            cur.execute(
                """SELECT c.id_chat, c.cliente_nombre, c.cliente_email, c.nro_guia, c.estado,
                          c.id_usuario_atendiendo, c.nombre_usuario_atendiendo,
                          c.fecha_creacion, c.fecha_actualizacion,
                          (SELECT COUNT(*) FROM mensajes_soporte m WHERE m.id_chat = c.id_chat) AS total_mensajes,
                          (SELECT mensaje FROM mensajes_soporte m WHERE m.id_chat = c.id_chat ORDER BY id_mensaje DESC LIMIT 1) AS ultimo_mensaje,
                          (SELECT fecha_envio FROM mensajes_soporte m WHERE m.id_chat = c.id_chat ORDER BY id_mensaje DESC LIMIT 1) AS fecha_ultimo_mensaje
                   FROM chats_soporte c WHERE c.estado <> 'cerrado'
                   ORDER BY c.fecha_creacion, c.id_chat"""
            )
            chats = cur.fetchall()
            for chat in chats:
                politica = ChatSoporte(chat)
                chat["puede_ver"] = politica.puede_leer(id_usuario, operador["tipo_usuario"])
                chat["puede_finalizar"] = politica.puede_finalizar(id_usuario, operador["tipo_usuario"])
                if not chat["puede_ver"]:
                    chat["ultimo_mensaje"] = None
                    chat["cliente_email"] = None
            return {
                "sin_atender": [c for c in chats if c["estado"] == "sin_atender"],
                "en_progreso": [c for c in chats if c["estado"] == "en_progreso"],
                "total": len(chats),
            }

    def agente_tiene_chat_en_progreso(self, id_usuario):
        with self._transaccion() as cur:
            self._operador(cur, id_usuario)
            cur.execute("SELECT * FROM chats_soporte WHERE operador_activo = %s", (id_usuario,))
            fila = cur.fetchone()
            return self._sin_token(fila) if fila else None

    def _asignar(self, cur, chat, operador):
        politica = ChatSoporte(chat)
        cambia = politica.asignar(operador["id_usuario"])
        if not cambia:
            return
        # El bloqueo del usuario serializa tomas de chats distintos del mismo operador.
        cur.execute("SELECT id_chat FROM chats_soporte WHERE operador_activo = %s", (operador["id_usuario"],))
        actual = cur.fetchone()
        if actual and actual["id_chat"] != chat["id_chat"]:
            raise SoporteError("Finalizá tu conversación actual antes de tomar otra.", 409, "OPERATOR_BUSY")
        cur.execute(
            """UPDATE chats_soporte SET estado = 'en_progreso', id_usuario_atendiendo = %s,
                   nombre_usuario_atendiendo = %s WHERE id_chat = %s""",
            (operador["id_usuario"], operador["nombre"], chat["id_chat"]),
        )
        chat.update(estado="en_progreso", id_usuario_atendiendo=operador["id_usuario"])
        self._insertar_mensaje(cur, chat["id_chat"], "soporte", operador["nombre"],
                               f"¡Hola! Soy {operador['nombre']} del equipo de soporte FormoPack. ¿En qué puedo ayudarte?")

    def tomar_chat(self, id_chat, id_usuario):
        with self._transaccion() as cur:
            operador = self._operador(cur, id_usuario, True)
            chat = self._chat(cur, id_chat)
            self._asignar(cur, chat, operador)

    def enviar_staff(self, id_chat, id_usuario, texto):
        mensaje = MensajeSoporte(texto)
        with self._transaccion() as cur:
            operador = self._operador(cur, id_usuario, True)
            chat = self._chat(cur, id_chat)
            if chat["estado"] == "sin_atender":
                self._asignar(cur, chat, operador)
            ChatSoporte(chat).validar_respuesta(id_usuario)
            return self._insertar_mensaje(cur, id_chat, "soporte", operador["nombre"], mensaje.texto)

    @staticmethod
    def _cerrar(cur, chat, id_usuario=None):
        cur.execute("DELETE FROM mensajes_soporte WHERE id_chat = %s", (chat["id_chat"],))
        cur.execute(
            """UPDATE chats_soporte SET estado = 'cerrado', fecha_cierre = NOW(), id_usuario_cierre = %s
               WHERE id_chat = %s AND estado <> 'cerrado'""", (id_usuario, chat["id_chat"]),
        )

    def finalizar_staff(self, id_chat, id_usuario):
        with self._transaccion() as cur:
            operador = self._operador(cur, id_usuario, True)
            chat = self._chat(cur, id_chat)
            ChatSoporte(chat).validar_cierre(id_usuario, operador["tipo_usuario"])
            self._cerrar(cur, chat, id_usuario)
            logger.info("Cierre de soporte: chat #%s por usuario #%s", id_chat, id_usuario)

    def finalizar_cliente(self, token):
        if not token:
            return
        with self._transaccion() as cur:
            cur.execute("SELECT * FROM chats_soporte WHERE session_id = %s FOR UPDATE", (token,))
            chat = cur.fetchone()
            if chat:
                self._cerrar(cur, chat)
