"""Protección criptográfica y límites persistentes de recuperación."""

import hashlib
import hmac
from datetime import timedelta


class ProtectorCodigoRecuperacion:
    """HMAC evita probar un OTP corto con una copia de la base solamente."""

    def __init__(self, clave: str):
        if not clave:
            raise ValueError("La clave de protección es obligatoria")
        self._clave = clave.encode("utf-8")

    def verificar(self, codigo: str, id_usuario: int, verificador: str) -> bool:
        return hmac.compare_digest(self.proteger(codigo, id_usuario), verificador)

    def proteger(self, codigo: str, id_usuario: int) -> str:
        contenido = f"formopack:otp:v1:{id_usuario}:{codigo}".encode("utf-8")
        return hmac.new(self._clave, contenido, hashlib.sha256).hexdigest()

    def clave_cuenta(self, email: str) -> str:
        contenido = f"formopack:limite:v1:{email.strip().lower()}".encode("utf-8")
        return hmac.new(self._clave, contenido, hashlib.sha256).hexdigest()


class LimiteSolicitudesRecuperacion:
    """Hasta cinco emisiones por hora y un minuto entre emisiones por cuenta.

    El cursor debe pertenecer a la transacción de recuperación. La fila se
    bloquea en MySQL para compartir el presupuesto entre procesos e instancias.
    """

    MAX_SOLICITUDES = 5
    VENTANA = timedelta(hours=1)
    INTERVALO = timedelta(minutes=1)

    def admitir(self, cursor, clave_cuenta: str) -> bool:
        cursor.execute(
            """INSERT INTO limites_recuperacion
                   (clave_cuenta, ventana_inicio, solicitudes, ultimo_envio)
               VALUES (%s, CURRENT_TIMESTAMP, 0, NULL)
               ON DUPLICATE KEY UPDATE clave_cuenta = VALUES(clave_cuenta)""", (clave_cuenta,),
        )
        cursor.execute(
            """SELECT ventana_inicio, solicitudes, ultimo_envio,
                      CURRENT_TIMESTAMP AS ahora
               FROM limites_recuperacion WHERE clave_cuenta = %s FOR UPDATE""",
            (clave_cuenta,),
        )
        fila = cursor.fetchone()
        ahora = fila["ahora"]
        inicio = fila["ventana_inicio"]
        solicitudes = int(fila["solicitudes"])
        if ahora - inicio >= self.VENTANA:
            inicio, solicitudes = ahora, 0
        ultimo = fila["ultimo_envio"]
        if solicitudes >= self.MAX_SOLICITUDES or (ultimo and ahora - ultimo < self.INTERVALO):
            return False
        cursor.execute(
            """UPDATE limites_recuperacion
               SET ventana_inicio = %s, solicitudes = %s, ultimo_envio = %s
               WHERE clave_cuenta = %s""",
            (inicio, solicitudes + 1, ahora, clave_cuenta),
        )
        return True
