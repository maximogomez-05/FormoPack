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

        # Versión HTML profesional con colores premium
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f4f8; margin: 0; padding: 30px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.05); border: 1px solid #e0e6ef; }}
                .header {{ background: linear-gradient(135deg, #0a192f 0%, #004481 100%); color: #ffffff; padding: 25px 30px; text-align: center; border-bottom: 4px solid {color_estado}; }}
                .header h1 {{ margin: 0; font-size: 26px; letter-spacing: 1px; font-weight: 800; }}
                .header span {{ font-weight: 300; font-size: 14px; opacity: 0.8; letter-spacing: 2px; text-transform: uppercase; display: block; margin-top: 5px; }}
                .content {{ padding: 35px 40px; color: #1a2332; line-height: 1.6; }}
                .status-container {{ text-align: center; margin: 25px 0 35px; }}
                .status-badge {{ display: inline-block; padding: 10px 24px; background-color: {color_estado}; color: #ffffff; font-weight: bold; border-radius: 30px; font-size: 15px; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 4px 12px {color_estado}40; }}
                .details-table {{ width: 100%; border-collapse: collapse; background: #f8fafd; border-radius: 8px; overflow: hidden; }}
                .details-table th, .details-table td {{ padding: 16px; border-bottom: 1px solid #e0e6ef; text-align: left; font-size: 15px; }}
                .details-table tr:last-child th, .details-table tr:last-child td {{ border-bottom: none; }}
                .details-table th {{ color: #6c757d; font-weight: 600; width: 40%; background: #f0f4f8; }}
                .details-table td {{ font-weight: 700; color: #0a192f; }}
                .footer {{ background-color: #f8fafd; padding: 20px; text-align: center; color: #6c757d; font-size: 13px; border-top: 1px solid #e0e6ef; }}
                .btn {{ display: inline-block; background-color: #004481; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: bold; font-size: 15px; margin-top: 30px; box-shadow: 0 4px 12px rgba(0,68,129,0.2); transition: background 0.3s; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>FormoPack</h1>
                    <span>Sistema Express</span>
                </div>
                <div class="content">
                    <p style="font-size: 17px; margin-top: 0;"><strong>Hola,</strong></p>
                    <p style="font-size: 16px; color: #4a5568;">Te informamos que ha habido una actualización en el estado de tu envío.</p>
                    
                    <div class="status-container">
                        <span class="status-badge">{estado.replace('_', ' ')}</span>
                    </div>

                    <table class="details-table">
                        <tr>
                            <th>Número de Guía</th>
                            <td style="color: #004481;">{envio.nro_guia}</td>
                        </tr>
                        <tr>
                            <th>Destino</th>
                            <td>{envio.direccion_destino}</td>
                        </tr>
                        <tr>
                            <th>Bultos</th>
                            <td>{envio.cantidad_bultos}</td>
                        </tr>
                        <tr>
                            <th>Modalidad</th>
                            <td style="text-transform: capitalize;">{envio.modalidad_pago}</td>
                        </tr>
                        """
        
        if observacion:
            html_content += f"""
                        <tr>
                            <th>Observación</th>
                            <td style="color: #c62828;">{observacion}</td>
                        </tr>"""

        html_content += f"""
                    </table>

                    <div style="text-align: center;">
                        <a href="{EmailConfig.BASE_URL if hasattr(EmailConfig, 'BASE_URL') else 'http://localhost:5050'}/" class="btn">Rastrear mi Envío</a>
                    </div>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">Este es un mensaje automático generado por <strong>FormoPack Express</strong>.</p>
                    <p style="margin: 0; opacity: 0.7;">&copy; 2026 FormoPack. Todos los derechos reservados.</p>
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
