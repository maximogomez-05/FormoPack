"""Outbox transaccional de avisos operativos. Nunca almacena códigos OTP."""

import hashlib
import json
import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from html import escape
from mysql.connector import Error as MySQLError

from app.core.database import DatabaseManager
from app.services.validacion_entrada import ValidacionEntrada
from app.utils.exceptions import ValidationError
from config.settings import EmailConfig

logger = logging.getLogger(__name__)


class TransporteSMTP:
    """Una sesión acotada por mensaje; los fallos llegan al procesador."""

    def enviar(self, trabajo):
        if not EmailConfig.USER or not EmailConfig.PASSWORD:
            raise RuntimeError("SMTP_NO_CONFIGURADO")
        contenido = json.loads(trabajo["contenido"])
        mensaje = EmailMessage()
        mensaje["From"] = f"FormoPack Express <{EmailConfig.USER}>"
        mensaje["To"] = trabajo["destinatario"]
        mensaje["Subject"] = contenido["asunto"]
        # Estable en reintentos: ayuda a identificar duplicados, no garantiza deduplicación SMTP.
        mensaje["Message-ID"] = f'<{trabajo["clave_evento"]}@formopackexpress.tech>'
        mensaje.set_content(contenido["texto"])
        texto_html = escape(contenido["texto"]).replace("\n", "<br>")
        mensaje.add_alternative(
            '<html lang="es"><body style="background:#f4f6f9;font-family:Arial,sans-serif;padding:24px">'
            '<div style="max-width:600px;margin:auto;background:white;border:1px solid #dce3eb">'
            '<div style="background:#004481;color:white;padding:20px;font-size:22px;font-weight:bold">FormoPack Express</div>'
            f'<div style="padding:24px;color:#102b44;line-height:1.6">{texto_html}</div>'
            '<div style="padding:16px;color:#64748b">Aviso operativo automático · FormoPack</div>'
            '</div></body></html>', subtype="html")
        contexto = ssl.create_default_context()
        if EmailConfig.PORT == 465:
            servidor = smtplib.SMTP_SSL(EmailConfig.HOST, EmailConfig.PORT, timeout=15, context=contexto)
        else:
            servidor = smtplib.SMTP(EmailConfig.HOST, EmailConfig.PORT, timeout=15)
        try:
            if EmailConfig.PORT != 465:
                servidor.starttls(context=contexto)
            servidor.login(EmailConfig.USER, EmailConfig.PASSWORD)
            rechazados = servidor.send_message(mensaje)
            if rechazados:
                raise smtplib.SMTPRecipientsRefused(rechazados)
        finally:
            # Un QUIT fallido después de DATA aceptado no cambia el resultado del envío.
            try:
                servidor.quit()
            except (OSError, smtplib.SMTPException):
                servidor.close()


class ColaNotificaciones:
    MAX_INTENTOS = 5
    LEASE_SEGUNDOS = 300

    def __init__(self, db_manager=None, transporte=None):
        self.db = db_manager or DatabaseManager.get_instance()
        self.transporte = transporte or TransporteSMTP()

    @staticmethod
    def encolar(cur, evento, destinatario, asunto, texto):
        try:
            correo = ValidacionEntrada.email(destinatario)
        except ValidationError:
            logger.warning("Aviso omitido: destinatario inválido")
            return False
        if not correo:
            return False
        correo = correo.lower()
        clave = hashlib.sha256(f"{evento}:{correo}".encode()).hexdigest()
        cur.execute("""INSERT INTO notificaciones_operativas (clave_evento,destinatario,contenido)
            VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE clave_evento=VALUES(clave_evento)""",
            (clave, correo, json.dumps({"asunto": asunto, "texto": texto}, ensure_ascii=False)))
        return True

    @staticmethod
    def encolar_historial(cur, id_historial):
        """Se ejecuta con el MISMO cursor y transacción que el cambio logístico."""
        cur.execute("""SELECT h.id_historial,h.estado,h.observacion,e.nro_guia,
            r.email AS remitente_email,d.email AS destinatario_email
            FROM historial_estados h JOIN envios e ON e.id_envio=h.id_envio
            JOIN clientes r ON r.id_cliente=e.id_remitente
            JOIN clientes d ON d.id_cliente=e.id_destinatario WHERE h.id_historial=%s""", (id_historial,))
        fila = cur.fetchone()
        if not fila:
            return
        if not isinstance(fila, dict):
            fila = dict(zip([col[0] for col in cur.description], fila))
        # Un mismo correo en ambos roles recibe un solo aviso por evento.
        for rol in ("destinatario", "remitente"):
            estado = fila["estado"]
            mensaje = {
                "recibido": "La encomienda fue recibida en mostrador.",
                "en_planta": "La encomienda está en planta, preparada para despacho.",
                "en_ruta": "La encomienda salió a reparto hacia su destino.",
                "entregado": "La encomienda fue entregada correctamente.",
                "fallido": "No se pudo completar la visita. Se gestionará un reintento si corresponde.",
                "devolucion": "Se inició el retorno de la encomienda a la central de Formosa Capital.",
                "retiro_remitente": "La encomienda está en central para retiro por el remitente registrado con DNI. No corresponde retiro por el destinatario.",
                "devuelto_remitente": "El remitente registrado retiró la encomienda en central.",
            }.get(estado, f"Estado actualizado: {estado.replace('_', ' ')}.")
            texto = (f"FormoPack Express\n\nGuía: {fila['nro_guia']}\n{mensaje}\n"
                     f"\nSeguimiento: https://formopackexpress.tech/admin/tracking?guia={fila['nro_guia']}\n")
            ColaNotificaciones.encolar(cur, f"historial:{id_historial}", fila[f"{rol}_email"],
                f"FormoPack · {fila['nro_guia']} · {estado.replace('_', ' ')}", texto)

    def reclamar(self):
        # InnoDB puede resolver dos scans concurrentes eligiendo una víctima.
        # Reintentar la transacción completa, nunca el envío SMTP.
        for _ in range(3):
            try:
                return self._reclamar_transaccion()
            except MySQLError as exc:
                if exc.errno not in (1213, 1205):
                    raise
        logger.warning("Avisos operativos: reclamación pospuesta por concurrencia")
        return None

    def _reclamar_transaccion(self):
        """UPDATE atómico: dos procesadores no reciben el mismo token vigente."""
        token = uuid.uuid4().hex
        with self.db.cursor() as cur:
            cur.execute("""UPDATE notificaciones_operativas
                SET estado='fallido',token=NULL,bloqueo_hasta=NULL,ultimo_error='INTENTOS_AGOTADOS'
                WHERE estado='procesando' AND bloqueo_hasta<=NOW() AND intentos>=%s""", (self.MAX_INTENTOS,))
            cur.execute("""UPDATE notificaciones_operativas SET estado='procesando',token=%s,
                bloqueo_hasta=DATE_ADD(NOW(),INTERVAL %s SECOND),intentos=intentos+1
                WHERE intentos<%s AND ((estado='pendiente' AND disponible_en<=NOW())
                    OR (estado='procesando' AND bloqueo_hasta<=NOW()))
                ORDER BY id_notificacion LIMIT 1""", (token, self.LEASE_SEGUNDOS, self.MAX_INTENTOS))
            if not cur.rowcount:
                return None
            cur.execute("SELECT * FROM notificaciones_operativas WHERE token=%s", (token,))
            return cur.fetchone()

    def procesar(self, limite=20):
        if not 1 <= limite <= 100:
            raise ValueError("El límite debe estar entre 1 y 100")
        enviados = 0
        for _ in range(limite):
            trabajo = self.reclamar()
            if not trabajo:
                break
            try:
                self.transporte.enviar(trabajo)
            except Exception as exc:
                # Nunca persistir el texto SMTP: puede contener direcciones o credenciales.
                codigo = type(exc).__name__[:80]
                rechazo_permanente = isinstance(exc, smtplib.SMTPRecipientsRefused) and bool(exc.recipients) and all(
                    500 <= respuesta[0] <= 599 for respuesta in exc.recipients.values())
                definitivo = trabajo["intentos"] >= self.MAX_INTENTOS or rechazo_permanente
                espera = min(3600, 60 * 2 ** (trabajo["intentos"] - 1))
                with self.db.cursor() as cur:
                    cur.execute("""UPDATE notificaciones_operativas SET estado=%s,ultimo_error=%s,
                        disponible_en=DATE_ADD(NOW(),INTERVAL %s SECOND),token=NULL,bloqueo_hasta=NULL
                        WHERE id_notificacion=%s AND token=%s AND estado='procesando'""",
                        ("fallido" if definitivo else "pendiente", codigo, espera, trabajo["id_notificacion"], trabajo["token"]))
                logger.warning("Aviso operativo #%s: %s", trabajo["id_notificacion"], codigo)
            else:
                with self.db.cursor() as cur:
                    cur.execute("""UPDATE notificaciones_operativas SET estado='enviado',enviado_en=NOW(),
                        ultimo_error=NULL,token=NULL,bloqueo_hasta=NULL
                        WHERE id_notificacion=%s AND token=%s AND estado='procesando'""",
                        (trabajo["id_notificacion"], trabajo["token"]))
                    enviados += cur.rowcount
        return enviados
