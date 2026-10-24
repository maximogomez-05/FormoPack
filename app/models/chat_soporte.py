"""Políticas del canal de soporte uno a uno (RF 5.6)."""

from app.utils.exceptions import SoporteError


class ChatSoporte:
    def __init__(self, fila: dict):
        self._estado = fila["estado"]
        self._id_operador = fila.get("id_usuario_atendiendo")

    @property
    def cerrado(self) -> bool:
        return self._estado == "cerrado"

    def puede_leer(self, id_usuario: int, rol: str) -> bool:
        return rol == "administrador" or self._id_operador == id_usuario or self._estado == "sin_atender"

    def validar_lectura(self, id_usuario: int, rol: str) -> None:
        if not self.puede_leer(id_usuario, rol):
            raise SoporteError("La conversación está asignada a otro operador.", 403, "SUPPORT_FORBIDDEN")

    def asignar(self, id_usuario: int) -> bool:
        if self.cerrado:
            raise SoporteError("La conversación ya fue finalizada.", 409, "CHAT_CLOSED")
        if self._estado == "en_progreso":
            if self._id_operador != id_usuario:
                raise SoporteError("La conversación ya está siendo atendida por otro operador.", 409, "CHAT_ASSIGNED")
            return False
        self._estado, self._id_operador = "en_progreso", id_usuario
        return True

    def validar_respuesta(self, id_usuario: int) -> None:
        if self.cerrado:
            raise SoporteError("La conversación ya fue finalizada.", 409, "CHAT_CLOSED")
        if self._estado != "en_progreso" or self._id_operador != id_usuario:
            raise SoporteError("Solo el operador asignado puede responder.", 403, "SUPPORT_FORBIDDEN")

    def puede_finalizar(self, id_usuario: int, rol: str) -> bool:
        return rol == "administrador" or self._id_operador == id_usuario

    def validar_cierre(self, id_usuario: int, rol: str) -> None:
        if not self.puede_finalizar(id_usuario, rol):
            raise SoporteError("No tenés permiso para finalizar esta conversación.", 403, "SUPPORT_FORBIDDEN")


class MensajeSoporte:
    MAX_CARACTERES = 2000

    def __init__(self, texto: str):
        if not isinstance(texto, str) or not texto.strip() or len(texto.strip()) > self.MAX_CARACTERES or "\x00" in texto:
            raise SoporteError("Ingresá un mensaje de entre 1 y 2000 caracteres.")
        self._texto = texto.strip()

    @property
    def texto(self) -> str:
        return self._texto
