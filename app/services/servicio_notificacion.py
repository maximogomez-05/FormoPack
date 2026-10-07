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

        # Diccionario de colores según estado
        colores = {
            "recibido": "#1565c0",
            "en_planta": "#f57f17",
            "en_ruta": "#2e7d32",
            "entregado": "#1b5e20",
            "fallido": "#c62828",
            "devolucion": "#c62828",
            "siniestro": "#000000",
        }
        color_estado = colores.get(estado.lower(), "#004481")

        msg = EmailMessage()
        msg['Subject'] = f"Actualización de Envío: {envio.nro_guia} - FormoPack"
        msg['From'] = f"FormoPack Express <{EmailConfig.USER}>"
        msg['To'] = ", ".join(emails_destino)

        # Versión texto plano (fallback)
        cuerpo_texto = f"FormoPack Express\n\nTu envío {envio.nro_guia} está ahora: {estado.upper()}.\n"
        if observacion:
            cuerpo_texto += f"Observación: {observacion}\n"
        cuerpo_texto += f"\nDestino: {envio.direccion_destino}\nTotal bultos: {envio.cantidad_bultos}\n\nPodés seguir el estado completo en nuestro portal web."
        msg.set_content(cuerpo_texto)

        # Versión HTML profesional
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
                .header {{ background-color: #0a192f; color: #ffffff; padding: 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 1px; }}
                .content {{ padding: 30px; color: #333333; }}
                .status-badge {{ display: inline-block; padding: 8px 16px; background-color: {color_estado}; color: #ffffff; font-weight: bold; border-radius: 20px; font-size: 14px; text-transform: uppercase; margin: 15px 0; }}
                .details-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .details-table th, .details-table td {{ padding: 12px; border-bottom: 1px solid #eeeeee; text-align: left; font-size: 14px; }}
                .details-table th {{ color: #6c757d; font-weight: normal; width: 40%; }}
                .details-table td {{ font-weight: 600; color: #333333; }}
                .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; color: #6c757d; font-size: 12px; border-top: 1px solid #eeeeee; }}
                .btn {{ display: inline-block; background-color: #004481; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>FormoPack Express</h1>
                </div>
                <div class="content">
                    <p style="font-size: 16px;">Hola,</p>
                    <p style="font-size: 16px;">Te informamos que ha habido una actualización en el estado de tu envío.</p>
                    
                    <div style="text-align: center;">
                        <span class="status-badge">{estado.replace('_', ' ')}</span>
                    </div>

                    <table class="details-table">
                        <tr>
                            <th>Número de Guía</th>
                            <td style="color: #004481; font-size: 16px;">{envio.nro_guia}</td>
                        </tr>
                        <tr>
                            <th>Destino</th>
                            <td>{envio.direccion_destino}</td>
                        </tr>
                        <tr>
                            <th>Cantidad de Bultos</th>
                            <td>{envio.cantidad_bultos}</td>
                        </tr>
                        <tr>
                            <th>Modalidad de Pago</th>
                            <td style="text-transform: capitalize;">{envio.modalidad_pago}</td>
                        </tr>
                        """
        
        if observacion:
            html_content += f"""
                        <tr>
                            <th>Observación</th>
                            <td style="color: #d32f2f;">{observacion}</td>
                        </tr>"""

        html_content += f"""
                    </table>

                    <div style="text-align: center;">
                        <a href="{EmailConfig.BASE_URL if hasattr(EmailConfig, 'BASE_URL') else 'http://localhost:5050'}/" class="btn">Rastrear Envío</a>
                    </div>
                </div>
                <div class="footer">
                    <p>Este es un mensaje automático generado por el Sistema FormoPack Express. Por favor, no responda a este correo.</p>
                    <p>&copy; 2026 FormoPack Express. Todos los derechos reservados.</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.add_alternative(html_content, subtype='html')

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
