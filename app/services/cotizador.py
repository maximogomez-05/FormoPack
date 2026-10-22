"""Motor de Cotización por Aforo con Regla Multibulto — RF 2.2 / RF 2.3."""

from __future__ import annotations
import logging
from typing import Optional

from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from config.settings import CotizadorConfig
from app.utils.exceptions import CotizacionError

from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


def _d(val) -> Decimal:
    """Convierte un valor numérico a Decimal de forma segura."""
    return Decimal(str(val))


def _redondear_moneda(val) -> float:
    """Redondea a 2 decimales bancarios exactos sin errores de punto flotante."""
    return float(_d(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class Cotizador:
    """Servicio de cotización de envíos."""

    def calcular_tarifa(
        self,
        bultos: list[Bulto],
        localidad: Localidad,
        valor_declarado: float = 0.0,
        seguro: Optional[Seguro] = None,
    ) -> dict:
        if not bultos:
            raise CotizacionError("El envio debe tener al menos un bulto para cotizar.")

        factor_zona = self._calcular_factor_zona(localidad)
        d_factor_zona = _d(factor_zona)
        d_tarifa_base_kg = _d(CotizadorConfig.TARIFA_BASE_KG)
        d_tarifa_minima = _d(CotizadorConfig.TARIFA_MINIMA)
        d_recargo_fragil = _d(CotizadorConfig.RECARGO_FRAGIL)
        d_desc_multibulto = _d(CotizadorConfig.DESCUENTO_MULTIBULTO)

        tarifas_por_bulto = []
        detalle_bultos = []

        for indice, bulto in enumerate(bultos):
            peso_aforo = bulto.calcular_aforo()
            d_peso_aforo = _d(peso_aforo)
            d_tarifa_base = d_peso_aforo * d_tarifa_base_kg * d_factor_zona

            # Regla Multibulto: 100% al primer bulto, 50% a los siguientes
            if indice == 0:
                descuento = 0.0
                d_tarifa_final = d_tarifa_base
            else:
                descuento = CotizadorConfig.DESCUENTO_MULTIBULTO
                d_tarifa_final = d_tarifa_base * (_d(1) - d_desc_multibulto)

            # Recargo por fragilidad
            recargo_fragil = 0.0
            if bulto.es_fragil:
                d_recargo = d_tarifa_final * d_recargo_fragil
                d_tarifa_final += d_recargo
                recargo_fragil = _redondear_moneda(d_recargo)

            # Tarifa mínima por bulto
            if d_tarifa_final < d_tarifa_minima:
                d_tarifa_final = d_tarifa_minima

            tarifa_final = _redondear_moneda(d_tarifa_final)

            tarifas_por_bulto.append(tarifa_final)
            detalle_bultos.append({
                "bulto_nro": indice + 1,
                "peso_real": bulto.peso_real,
                "peso_volumetrico": bulto.peso_volumetrico,
                "peso_aforo": peso_aforo,
                "tarifa_base": _redondear_moneda(d_tarifa_base),
                "descuento_multibulto": f"{int(descuento * 100)}%",
                "recargo_fragil": recargo_fragil,
                "tarifa_final": tarifa_final,
            })

        subtotal_flete = _redondear_moneda(sum(_d(t) for t in tarifas_por_bulto))

        # Cálculo de seguro
        costo_seguro = 0.0
        if seguro and valor_declarado > 0:
            costo_seguro = _redondear_moneda(seguro.calcular_costo_cobertura(valor_declarado))

        costo_total = _redondear_moneda(_d(subtotal_flete) + _d(costo_seguro))

        resultado = {
            "localidad_destino": localidad.nombre,
            "distancia_km": localidad.distancia_km,
            "factor_zona": factor_zona,
            "cantidad_bultos": len(bultos),
            "tarifas_por_bulto": tarifas_por_bulto,
            "subtotal_flete": subtotal_flete,
            "valor_declarado": valor_declarado,
            "costo_seguro": costo_seguro,
            "costo_total": costo_total,
            "detalle_bultos": detalle_bultos,
        }

        logger.info(
            "Cotizacion: %d bultos a %s (%s KM) = $%.2f",
            len(bultos), localidad.nombre, localidad.distancia_km, costo_total,
        )

        return resultado

    def _calcular_factor_zona(self, localidad: Localidad) -> float:
        """Calcula el factor multiplicador según la zona/corredor de la localidad.

        Corredores:
            - Urbano (0-50 KM): factor 1.0
            - Periurbano (51-150 KM): factor 1.5
            - Interior (151-300 KM): factor 2.0
            - Frontera (>300 KM): factor 2.5

        Args:
            localidad: Localidad de destino.

        Returns:
            Factor multiplicador de zona.
        """
        corredor = localidad.obtener_corredor_centro()
        factores = {
            "urbano": 1.0,
            "periurbano": 1.5,
            "interior": 2.0,
            "frontera": 2.5,
        }
        return factores.get(corredor, 1.0)
