"""Generador de Números de Guía únicos — RF 2."""

from __future__ import annotations
import logging
from datetime import datetime

import threading

logger = logging.getLogger(__name__)


class GeneradorGuia:
    """Servicio para generar números de guía únicos para envíos (Thread-Safe).

    Formato: FPX-YYYYMMDD-NNNN
    - FPX: Prefijo de FormoPack Express
    - YYYYMMDD: Fecha de generación
    - NNNN: Correlativo diario auto-incremental
    """

    _lock = threading.Lock()

    def __init__(self) -> None:
        self._ultimo_correlativo: int = 0
        self._fecha_actual: str = ""

    def generar_nro_guia(self, correlativo_db: int = 0) -> str:
        """Genera un número de guía único con formato FPX-YYYYMMDD-NNNN de forma atómica."""
        with self._lock:
            fecha_hoy = datetime.now().strftime("%Y%m%d")

            if fecha_hoy != self._fecha_actual or correlativo_db > self._ultimo_correlativo:
                self._fecha_actual = fecha_hoy
                self._ultimo_correlativo = correlativo_db

            self._ultimo_correlativo += 1
            nro_guia = f"FPX-{fecha_hoy}-{self._ultimo_correlativo:04d}"

            logger.info("Guía generada: %s", nro_guia)
            return nro_guia

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
