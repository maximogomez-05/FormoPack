"""Generador de Números de Guía únicos — RF 2."""

from __future__ import annotations
from datetime import datetime


class GeneradorGuia:
    """Reserva el correlativo diario en la misma transacción que el envío."""

    @staticmethod
    def reservar(cursor) -> str:
        fecha = datetime.now().strftime("%Y%m%d")
        cursor.execute("""
            INSERT INTO correlativos_guia (fecha, ultimo) VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE ultimo = ultimo + 1
        """, (fecha,))
        cursor.execute("SELECT ultimo FROM correlativos_guia WHERE fecha=%s", (fecha,))
        return f"FPX-{fecha}-{cursor.fetchone()[0]:04d}"

    def generar_nro_comprobante(self, tipo: str, correlativo_db: int = 0) -> str:
        """Genera un número de comprobante interno.

        Args:
            tipo: Tipo de comprobante (ej: 'REC' para recepción, 'ENT' para entrega).
            correlativo_db: Último correlativo registrado en la BD.

        Returns:
            Número de comprobante formateado.
        """
        fecha_hoy = datetime.now().strftime("%Y%m%d")
        nro = correlativo_db + 1
        return f"{tipo.upper()}-{fecha_hoy}-{nro:04d}"
