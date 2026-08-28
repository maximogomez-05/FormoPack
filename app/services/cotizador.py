"""Motor de Cotización por Aforo con Regla Multibulto — RF 2.2 / RF 2.3."""

from __future__ import annotations
import logging
from typing import Optional

from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from config.settings import CotizadorConfig
from app.utils.exceptions import CotizacionError

logger = logging.getLogger(__name__)


class Cotizador:
    """Servicio de cotización de envíos.

    Implementa el cálculo de tarifa evaluando:
    1. Zona de destino (distancia KM de la localidad).
    2. Peso de aforo de cada bulto (mayor entre real y volumétrico).
    3. Regla Multibulto: 100% al primer bulto, 50% de descuento a los siguientes.
    4. Recargo por fragilidad (opcional).
    5. Costo de seguro por excedente de valor declarado.

    Corresponde a la clase `Cotizador` del diagrama UML con método
    `calcularTarifa(envio, zona, bultos)`.
    """

    def calcular_tarifa(
        self,
        bultos: list[Bulto],
        localidad: Localidad,
        valor_declarado: float = 0.0,
        seguro: Optional[Seguro] = None,
    ) -> dict:
        """Calcula la tarifa total del envío.

        Args:
            bultos: Lista de bultos del envío.
            localidad: Localidad de destino.
            valor_declarado: Valor declarado del contenido.
            seguro: Instancia de Seguro (opcional).

        Returns:
            Diccionario con el desglose de la cotización:
            {
                "tarifas_por_bulto": [...],
                "subtotal_flete": float,
                "costo_seguro": float,
                "costo_total": float,
                "detalle_bultos": [...],
            }

        Raises:
            CotizacionError: Si no hay bultos o datos inválidos.
        """
        if not bultos:
            raise CotizacionError("El envio debe tener al menos un bulto para cotizar.")

        factor_zona = self._calcular_factor_zona(localidad)
        tarifas_por_bulto = []
        detalle_bultos = []

        for indice, bulto in enumerate(bultos):
            peso_aforo = bulto.calcular_aforo()
            tarifa_base = peso_aforo * CotizadorConfig.TARIFA_BASE_KG * factor_zona

            # Regla Multibulto: 100% al primer bulto, 50% a los siguientes
            if indice == 0:
                descuento = 0.0
                tarifa_final = tarifa_base
            else:
                descuento = CotizadorConfig.DESCUENTO_MULTIBULTO
                tarifa_final = tarifa_base * (1 - descuento)

            # Recargo por fragilidad
            recargo_fragil = 0.0
            if bulto.es_fragil:
                recargo_fragil = tarifa_final * CotizadorConfig.RECARGO_FRAGIL
                tarifa_final += recargo_fragil

            # Tarifa mínima por bulto
            tarifa_final = max(tarifa_final, CotizadorConfig.TARIFA_MINIMA)
            tarifa_final = round(tarifa_final, 2)

            tarifas_por_bulto.append(tarifa_final)
            detalle_bultos.append({
                "bulto_nro": indice + 1,
                "peso_real": bulto.peso_real,
                "peso_volumetrico": bulto.peso_volumetrico,
                "peso_aforo": peso_aforo,
                "tarifa_base": round(tarifa_base, 2),
                "descuento_multibulto": f"{int(descuento * 100)}%",
                "recargo_fragil": round(recargo_fragil, 2),
                "tarifa_final": tarifa_final,
            })

        subtotal_flete = round(sum(tarifas_por_bulto), 2)

        # Cálculo de seguro
        costo_seguro = 0.0
        if seguro and valor_declarado > 0:
            costo_seguro = seguro.calcular_costo_cobertura(valor_declarado)

        costo_total = round(subtotal_flete + costo_seguro, 2)

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
