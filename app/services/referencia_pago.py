"""Identidad de la orden preservada sin depender de metadata del checkout."""

import re


class ReferenciaPagoMP:
    @staticmethod
    def crear(id_orden):
        if not isinstance(id_orden, str) or not re.fullmatch(r"[0-9a-f]{32}", id_orden):
            raise ValueError("Identificador de orden inválido")
        return "FPMP-" + id_orden

    @staticmethod
    def leer(referencia):
        coincidencia = re.fullmatch(r"FPMP-([0-9a-f]{32})", referencia or "") if isinstance(referencia, str) else None
        return coincidencia.group(1) if coincidencia else None
