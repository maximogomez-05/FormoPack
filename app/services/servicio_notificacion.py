"""Servicio de Notificación (RF 5.4)."""

import smtplib
import logging
from email.message import EmailMessage
from typing import Optional

from config.settings import EmailConfig
from app.models.envio import Envio
from app.models.cliente import Cliente

logger = logging.getLogger(__name__)


class ServicioNotificacion:
    """Servicio para el envío de alertas automáticas (Email)."""

    def __init__(self) -> None:
        self.canal_preferencia = "email"

    def enviar_alerta_cambio_estado(
        self,
        envio: Envio,
        cliente: Cliente,
        nuevo_estado: Optional[str] = None,
        observacion: Optional[str] = None,
    ) -> None:
        """Envía una alerta por correo electrónico ante un cambio de estado.

        Args:
            envio: El envío que cambió de estado.
            cliente: Cliente al que se notifica (generalmente el remitente).
            nuevo_estado: El nuevo estado, o el estado actual del envío si no se provee.
            observacion: Observación o detalle adicional.
        """
        if self.canal_preferencia != "email":
            logger.warning("Canal de preferencia no es email, omitiendo alerta.")
            return

        if not EmailConfig.USER or not EmailConfig.PASSWORD:
            logger.warning("Credenciales SMTP no configuradas. Omitiendo notificación por email.")
            return

        estado = nuevo_estado or envio.estado_actual
        
        # Obtener emails de remitente y destinatario
        emails_destino = []
        if cliente and cliente.email:
            emails_destino.append(cliente.email)
            
        try:
            from app.core.database import DatabaseManager
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cur = conn.cursor(dictionary=True)
            
            # Buscar el cliente faltante (si cliente pasado es remitente, buscamos destinatario y viceversa)
            id_faltante = envio.id_destinatario if (cliente and cliente.id_cliente == envio.id_remitente) else envio.id_remitente
            cur.execute("SELECT email FROM clientes WHERE id_cliente = %s", (id_faltante,))
            row = cur.fetchone()
            if row and row.get("email"):
                emails_destino.append(row["email"])
                
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("No se pudo obtener el email del otro cliente: %s", e)

        # Filtrar repetidos y vacíos
        emails_destino = list(set([e for e in emails_destino if e]))

        if not emails_destino:
            logger.info("No hay correos registrados (ni remitente ni destinatario) para el envío %s", envio.nro_guia)
            return

        msg = EmailMessage()
        msg['Subject'] = f"FormoPack Alerta - Envío {envio.nro_guia} - {estado.upper()}"
        msg['From'] = EmailConfig.USER
        msg['To'] = ", ".join(emails_destino)

        cuerpo = f"Estimado/a Cliente,\n\n"
        cuerpo += f"Le informamos que el envío con número de guía {envio.nro_guia} ha cambiado de estado.\n\n"
        cuerpo += f"Nuevo Estado: {estado.upper()}\n"

        if observacion:
            cuerpo += f"Observación: {observacion}\n"

        cuerpo += "\nGracias por confiar en FormoPack Express."

        msg.set_content(cuerpo)

        try:
            if EmailConfig.PORT == 465:
                server = smtplib.SMTP_SSL(EmailConfig.HOST, EmailConfig.PORT)
            else:
                server = smtplib.SMTP(EmailConfig.HOST, EmailConfig.PORT)
                server.starttls()

            server.login(EmailConfig.USER, EmailConfig.PASSWORD)
            server.send_message(msg)
            server.quit()
            logger.info("Notificación enviada exitosamente para envío %s a %s", envio.nro_guia, msg['To'])
        except Exception as e:
            logger.warning("Error al enviar notificación por email (SMTP): %s", e)
