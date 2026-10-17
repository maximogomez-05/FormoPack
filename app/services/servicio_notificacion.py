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
        """RF 6.2: Envía alertas personalizadas al remitente Y al destinatario.

        - Al remitente: mensaje de seguimiento informativo ("Tu envío está en camino").
        - Al destinatario: mensaje de acción directa ("Tu paquete llegará hoy").
        """
        if self.canal_preferencia != "email":
            return

        if not EmailConfig.USER or not EmailConfig.PASSWORD:
            logger.warning("Credenciales SMTP no configuradas. Omitiendo notificación por email.")
            return

        estado = nuevo_estado or envio.estado_actual

        # --- Obtener ambos clientes de la BD ---
        remitente_email = None
        destinatario_email = None
        destinatario_nombre = None
        conn = None
        try:
            from app.core.database import DatabaseManager
            db = DatabaseManager.get_instance()
            conn = db.get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT nombre_completo, email FROM clientes WHERE id_cliente = %s", (envio.id_remitente,))
            row_rem = cur.fetchone()
            if row_rem:
                remitente_email = row_rem.get("email")
            cur.execute("SELECT nombre_completo, email FROM clientes WHERE id_cliente = %s", (envio.id_destinatario,))
            row_dest = cur.fetchone()
            if row_dest:
                destinatario_email = row_dest.get("email")
                destinatario_nombre = row_dest.get("nombre_completo", "")
            cur.close()
            conn.close()
            conn = None
        except Exception as e:
            logger.warning("No se pudo obtener datos de clientes para notificación: %s", e)
        finally:
            if conn:
                conn.close()

        # --- Mensajes personalizados por estado y rol ---
        mensajes_destinatario = {
            "en_planta": "Tu paquete está en nuestra planta y está siendo preparado para el despacho.",
            "en_ruta": "¡Tu paquete está en camino! El chofer ya salió a entregarlo. Estate atento.",
            "entregado": "¡Tu paquete fue entregado exitosamente! Gracias por confiar en FormoPack Express.",
            "fallido": "Se intentó entregar tu paquete pero no fue posible. Nos volvemos a contactar pronto.",
            "devolucion": "Tu paquete fue marcado para devolución al remitente.",
        }
        mensajes_remitente = {
            "en_planta": "Tu envío fue recibido en nuestra planta. Pronto será despachado a destino.",
            "en_ruta": "El envío que generaste ya está en ruta hacia su destino.",
            "entregado": "El envío que generaste fue entregado correctamente al destinatario.",
            "fallido": "El intento de entrega de tu envío falló. Se gestionará un reintento.",
            "devolucion": "Tu envío está siendo devuelto por no poder completar la entrega.",
        }

        msg_dest = mensajes_destinatario.get(estado, observacion or f"Estado actualizado: {estado}")
        msg_rem = mensajes_remitente.get(estado, observacion or f"Estado actualizado: {estado}")

        # --- Enviar al destinatario (siempre primero) ---
        if destinatario_email:
            asunto_dest = self._asunto_por_estado(estado, envio.nro_guia)
            self._enviar_email_individual(
                email_to=destinatario_email,
                nombre_to=destinatario_nombre or "destinatario",
                rol="destinatario",
                envio=envio,
                estado=estado,
                mensaje_principal=msg_dest,
                observacion=observacion,
                asunto=asunto_dest,
            )

        # --- Enviar al remitente ---
        if remitente_email and remitente_email != destinatario_email:
            asunto_rem = f"[Seguimiento] Tu envío {envio.nro_guia} — FormoPack"
            self._enviar_email_individual(
                email_to=remitente_email,
                nombre_to=cliente.nombre_completo if cliente else "remitente",
                rol="remitente",
                envio=envio,
                estado=estado,
                mensaje_principal=msg_rem,
                observacion=observacion,
                asunto=asunto_rem,
            )

        if not destinatario_email and not remitente_email:
            logger.info("Sin emails registrados para notificar el envío %s", envio.nro_guia)

    @staticmethod
    def _asunto_por_estado(estado: str, nro_guia: str) -> str:
        asuntos = {
            "en_ruta": f"🚚 Tu paquete {nro_guia} está en camino — FormoPack",
            "entregado": f"✅ Tu paquete {nro_guia} fue entregado — FormoPack",
            "fallido": f"⚠️ Intento de entrega fallido — {nro_guia} — FormoPack",
            "devolucion": f"📦 Devolución iniciada — {nro_guia} — FormoPack",
        }
        return asuntos.get(estado, f"Actualización de tu envío {nro_guia} — FormoPack")

    def _enviar_email_individual(
        self,
        email_to: str,
        nombre_to: str,
        rol: str,
        envio: Envio,
        estado: str,
        mensaje_principal: str,
        observacion: Optional[str],
        asunto: str,
    ) -> None:
        """Construye y envía un email HTML a un destinatario único."""
        colores = {
            "recibido": "#1565c0", "en_planta": "#f57f17", "en_ruta": "#2e7d32",
            "entregado": "#1b5e20", "fallido": "#c62828", "devolucion": "#c62828",
            "siniestro": "#000000",
        }
        color_estado = colores.get(estado.lower(), "#004481")

        saludo = "Hola" if not nombre_to else f"Hola, {nombre_to.split()[0].capitalize()}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f4f8; margin: 0; padding: 30px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.05); border: 1px solid #e0e6ef; }}
            .header {{ background: linear-gradient(135deg, #0a192f 0%, #004481 100%); color: #fff; padding: 25px 30px; text-align: center; border-bottom: 4px solid {color_estado}; }}
            .header h1 {{ margin: 0; font-size: 26px; font-weight: 800; }}
            .header span {{ font-size: 13px; opacity: 0.8; display: block; margin-top: 4px; }}
            .content {{ padding: 35px 40px; color: #1a2332; line-height: 1.7; }}
            .status-badge {{ display:inline-block; padding:10px 24px; background:{color_estado}; color:#fff; font-weight:bold; border-radius:30px; font-size:15px; text-transform:uppercase; letter-spacing:1px; }}
            .highlight-box {{ background:#f0f7ff; border-left: 4px solid {color_estado}; padding: 16px 20px; border-radius: 6px; margin: 20px 0; font-size: 15px; color: #1a2332; }}
            .details-table {{ width:100%; border-collapse:collapse; background:#f8fafd; border-radius:8px; overflow:hidden; }}
            .details-table th, .details-table td {{ padding:14px 16px; border-bottom:1px solid #e0e6ef; text-align:left; font-size:14px; }}
            .details-table tr:last-child th, .details-table tr:last-child td {{ border-bottom:none; }}
            .details-table th {{ color:#6c757d; font-weight:600; width:40%; background:#f0f4f8; }}
            .details-table td {{ font-weight:700; color:#0a192f; }}
            .footer {{ background:#f8fafd; padding:20px; text-align:center; color:#6c757d; font-size:13px; border-top:1px solid #e0e6ef; }}
            .btn {{ display:inline-block; background:#004481; color:#fff; text-decoration:none; padding:14px 28px; border-radius:8px; font-weight:bold; font-size:15px; margin-top:25px; }}
        </style></head>
        <body><div class="container">
            <div class="header"><h1>FormoPack</h1><span>Sistema Express de Logística</span></div>
            <div class="content">
                <p style="font-size:17px; margin-top:0;"><strong>{saludo}</strong></p>
                <div class="highlight-box">{mensaje_principal}</div>
                <div style="text-align:center; margin:20px 0;">
                    <span class="status-badge">{estado.replace('_', ' ')}</span>
                </div>
                <table class="details-table">
                    <tr><th>Número de Guía</th><td style="color:#004481;">{envio.nro_guia}</td></tr>
                    <tr><th>Destino</th><td>{envio.direccion_destino}</td></tr>
                    <tr><th>Bultos</th><td>{envio.cantidad_bultos}</td></tr>
                    <tr><th>Modalidad de Pago</th><td style="text-transform:capitalize;">{envio.modalidad_pago}</td></tr>
                    {('<tr><th>Observación</th><td style="color:#c62828;">' + observacion + '</td></tr>') if observacion else ''}
                </table>
                <div style="text-align:center;">
                    <a href="{EmailConfig.BASE_URL if hasattr(EmailConfig, 'BASE_URL') else 'http://localhost:5050'}/admin/tracking" class="btn">Rastrear mi Envío</a>
                </div>
            </div>
            <div class="footer">
                <p style="margin:0 0 8px;">Este es un mensaje automático de <strong>FormoPack Express</strong>.</p>
                <p style="margin:0; opacity:.7;">© 2026 FormoPack. Todos los derechos reservados.</p>
            </div>
        </div></body></html>
        """

        msg = EmailMessage()
        msg['Subject'] = asunto
        msg['From'] = f"FormoPack Express <{EmailConfig.USER}>"
        msg['To'] = email_to
        msg.set_content(f"FormoPack Express\n\n{mensaje_principal}\n\nGuía: {envio.nro_guia}\nDestino: {envio.direccion_destino}\n")
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
            logger.info("[RF 6.2] Email enviado a %s (%s) para guía %s", email_to, rol, envio.nro_guia)
        except Exception as e:
            logger.warning("Error al enviar notificación por email (SMTP) a %s: %s", email_to, e)
