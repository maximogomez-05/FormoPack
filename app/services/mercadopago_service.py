"""Servicio de integración con Mercado Pago — RF 2.5 (Checkout Pro).

Encapsula toda la lógica de comunicación con la API de Mercado Pago.
El resto del sistema sólo interactúa con esta clase, nunca directamente con el SDK.
"""

import logging
import mercadopago

from config.settings import MercadoPagoConfig

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """Servicio POO para generar y consultar preferencias de pago.

    Utiliza el patrón de inicialización lazy: el SDK solo se instancia
    si las credenciales están correctamente configuradas en el .env.
    """

    def __init__(self) -> None:
        self._cfg = MercadoPagoConfig
        if not self._cfg.esta_configurado():
            raise EnvironmentError(
                "Las credenciales de Mercado Pago no están configuradas. "
                "Completá MP_ACCESS_TOKEN y MP_PUBLIC_KEY en el archivo .env."
            )
        self._sdk = mercadopago.SDK(self._cfg.ACCESS_TOKEN)

    # ─────────────────────────────────────────
    # Generación de Preferencia (Checkout Pro)
    # ─────────────────────────────────────────

    def crear_preferencia(self, nro_guia: str, descripcion: str, monto: float) -> dict:
        """Genera una preferencia de pago en Mercado Pago para un envío.

        Args:
            nro_guia:    Número de guía del envío (se usa como external_reference).
            descripcion: Descripción que el cliente verá en la pantalla de MP.
            monto:       Monto total a cobrar (en pesos argentinos).

        Returns:
            Diccionario con 'id' (preferencia MP), 'init_point' (URL Checkout Pro)
            y 'sandbox_init_point' (URL para pruebas).

        Raises:
            RuntimeError: Si la API de Mercado Pago rechaza la solicitud.
        """
        preference_data = {
            "items": [
                {
                    "title": f"FormoPack Express — Guía {nro_guia}",
                    "description": descripcion,
                    "quantity": 1,
                    "unit_price": float(round(monto, 2)),
                    "currency_id": "ARS",
                }
            ],
            "external_reference": nro_guia,
            "back_urls": {
                "success": self._cfg.SUCCESS_URL,
                "failure": self._cfg.FAILURE_URL,
                "pending": self._cfg.PENDING_URL,
            },
            "auto_return": "approved",
            "notification_url": self._cfg.WEBHOOK_URL,
            "statement_descriptor": "FORMOPACK EXPRESS",
            "expires": False,
        }

        try:
            resultado = self._sdk.preference().create(preference_data)
            response = resultado.get("response", {})
            status = resultado.get("status", 0)

            if status not in (200, 201) or "id" not in response:
                error_msg = response.get("message", "Error desconocido de Mercado Pago")
                logger.error("Error al crear preferencia MP (status %d): %s", status, error_msg)
                raise RuntimeError(f"Mercado Pago rechazó la solicitud: {error_msg}")

            logger.info(
                "Preferencia MP creada para guía %s — ID: %s",
                nro_guia, response["id"]
            )
            return {
                "id": response["id"],
                "init_point": response.get("init_point", ""),
                "sandbox_init_point": response.get("sandbox_init_point", ""),
            }

        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Excepción inesperada al crear preferencia MP: %s", e)
            raise RuntimeError(f"Error al conectar con Mercado Pago: {e}") from e

    # ─────────────────────────────────────────
    # Consulta de estado de pago (Webhook)
    # ─────────────────────────────────────────

    def obtener_pago(self, payment_id: str) -> dict | None:
        """Consulta el estado de un pago individual por su ID de Mercado Pago.

        Args:
            payment_id: ID del pago devuelto por MP en el webhook o redirect.

        Returns:
            Diccionario con status, external_reference (nro_guia) y monto.
            None si no se puede obtener el pago.
        """
        try:
            resultado = self._sdk.payment().get(payment_id)
            response = resultado.get("response", {})
            status_code = resultado.get("status", 0)

            if status_code != 200:
                logger.warning("No se pudo obtener pago MP ID %s (status %d)", payment_id, status_code)
                return None

            return {
                "id": str(response.get("id", "")),
                "status": response.get("status", ""),          # approved / rejected / pending
                "status_detail": response.get("status_detail", ""),
                "external_reference": response.get("external_reference", ""),  # nro_guia
                "monto": float(response.get("transaction_amount", 0)),
                "metodo": response.get("payment_method_id", ""),
                "fecha": response.get("date_approved", ""),
            }

        except Exception as e:
            logger.error("Error al consultar pago MP %s: %s", payment_id, e)
            return None

    @property
    def public_key(self) -> str:
        """Devuelve la Public Key para el SDK de JS del frontend."""
        return self._cfg.PUBLIC_KEY
