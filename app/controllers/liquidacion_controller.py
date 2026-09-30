"""Controlador de Liquidaciones de Chofer (RF 5.6).

Genera reportes de rendimiento por chofer en un rango de fechas,
cruzando hojas_de_ruta, envios e intentos_entrega.
"""

import logging
from datetime import date
from typing import List, Optional

from app.core.database import DatabaseManager
from app.models.liquidacion import Liquidacion
from app.utils.exceptions import DatabaseQueryError, ValidationError

logger = logging.getLogger(__name__)


class LiquidacionController:
    """Gestiona las consultas de liquidación de choferes."""

    def __init__(self) -> None:
        self._db = DatabaseManager.get_instance()

    def obtener_choferes_con_actividad(self) -> list[dict]:
        """Lista choferes activos que tienen al menos una hoja de ruta asignada."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT DISTINCT u.id_usuario, u.nombre
                FROM usuarios u
                INNER JOIN hojas_de_ruta hr ON u.id_usuario = hr.id_chofer
                WHERE u.tipo_usuario = 'chofer'
                ORDER BY u.nombre ASC
            """)
            return cursor.fetchall()
        except Exception as e:
            logger.error("Error al obtener choferes con actividad: %s", e)
            return []
        finally:
            if conn:
                conn.close()

    def generar_liquidacion(
        self,
        id_chofer: int,
        fecha_desde: date,
        fecha_hasta: date,
    ) -> Optional[Liquidacion]:
        """Genera la liquidación de un chofer para un rango de fechas.

        Cruza hojas_de_ruta → envios → intentos_entrega para calcular:
        - Total de hojas de ruta asignadas
        - Total de envíos asignados
        - Entregados, fallidos y pendientes
        - Monto facturado total
        - Kilómetros recorridos estimados
        """
        if fecha_desde > fecha_hasta:
            raise ValidationError(
                field="fechas",
                reason="La fecha inicial no puede ser posterior a la fecha final",
            )

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Verificar que el chofer existe
            cursor.execute(
                "SELECT nombre FROM usuarios WHERE id_usuario = %s AND tipo_usuario = 'chofer'",
                (id_chofer,),
            )
            chofer = cursor.fetchone()
            if not chofer:
                raise ValidationError(field="chofer", reason="El chofer no existe")

            # Obtener hojas de ruta del período
            cursor.execute("""
                SELECT
                    hr.id_hoja_ruta,
                    hr.nro_despacho,
                    hr.fecha_emision,
                    v.patente,
                    COUNT(e.id_envio) AS cant_envios,
                    COALESCE(SUM(CASE WHEN e.estado_actual = 'entregado' THEN 1 ELSE 0 END), 0) AS entregados,
                    COALESCE(SUM(CASE WHEN e.estado_actual = 'fallido' THEN 1 ELSE 0 END), 0) AS fallidos,
                    COALESCE(SUM(CASE WHEN e.estado_actual NOT IN ('entregado', 'fallido') THEN 1 ELSE 0 END), 0) AS pendientes,
                    COALESCE(SUM(e.costo_total), 0) AS monto,
                    COALESCE(MAX(l.distancia_km), 0) AS max_distancia
                FROM hojas_de_ruta hr
                JOIN vehiculos v ON hr.id_vehiculo = v.id_vehiculo
                LEFT JOIN envios e ON e.id_hoja_ruta = hr.id_hoja_ruta
                LEFT JOIN localidades l ON e.id_localidad_destino = l.id_localidad
                WHERE hr.id_chofer = %s
                  AND DATE(hr.fecha_emision) BETWEEN %s AND %s
                GROUP BY hr.id_hoja_ruta
                ORDER BY hr.fecha_emision DESC
            """, (id_chofer, fecha_desde, fecha_hasta))
            hojas_rows = cursor.fetchall()

            # Calcular totales
            total_hojas = len(hojas_rows)
            total_envios = sum(int(h["cant_envios"]) for h in hojas_rows)
            total_entregados = sum(int(h["entregados"]) for h in hojas_rows)
            total_fallidos = sum(int(h["fallidos"]) for h in hojas_rows)
            total_pendientes = sum(int(h["pendientes"]) for h in hojas_rows)
            total_monto = sum(float(h["monto"]) for h in hojas_rows)
            total_km = sum(float(h["max_distancia"]) * 2 for h in hojas_rows)  # ida y vuelta

            # Detalle por hoja
            hojas_detalle = []
            for h in hojas_rows:
                hojas_detalle.append({
                    "id_hoja_ruta": h["id_hoja_ruta"],
                    "nro_despacho": h["nro_despacho"],
                    "fecha_emision": h["fecha_emision"],
                    "patente": h["patente"],
                    "cant_envios": int(h["cant_envios"]),
                    "entregados": int(h["entregados"]),
                    "fallidos": int(h["fallidos"]),
                    "pendientes": int(h["pendientes"]),
                    "monto": float(h["monto"]),
                    "max_distancia": float(h["max_distancia"]),
                })

            return Liquidacion(
                id_chofer=id_chofer,
                nombre_chofer=chofer["nombre"],
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                total_hojas=total_hojas,
                total_envios=total_envios,
                entregados=total_entregados,
                fallidos=total_fallidos,
                pendientes=total_pendientes,
                monto_facturado=total_monto,
                km_recorridos=total_km,
                hojas_detalle=hojas_detalle,
            )

        except ValidationError:
            raise
        except Exception as e:
            logger.error("Error al generar liquidación: %s", e)
            raise DatabaseQueryError(f"Error al generar liquidación: {e}")
        finally:
            if conn:
                conn.close()

    def generar_resumen_todos(
        self,
        fecha_desde: date,
        fecha_hasta: date,
    ) -> List[dict]:
        """Genera un resumen rápido de todos los choferes en el período."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    u.id_usuario AS id_chofer,
                    u.nombre AS nombre_chofer,
                    COUNT(DISTINCT hr.id_hoja_ruta) AS total_hojas,
                    COUNT(e.id_envio) AS total_envios,
                    COALESCE(SUM(CASE WHEN e.estado_actual = 'entregado' THEN 1 ELSE 0 END), 0) AS entregados,
                    COALESCE(SUM(CASE WHEN e.estado_actual = 'fallido' THEN 1 ELSE 0 END), 0) AS fallidos,
                    COALESCE(SUM(e.costo_total), 0) AS monto_facturado
                FROM usuarios u
                INNER JOIN hojas_de_ruta hr ON u.id_usuario = hr.id_chofer
                LEFT JOIN envios e ON e.id_hoja_ruta = hr.id_hoja_ruta
                WHERE u.tipo_usuario = 'chofer'
                  AND DATE(hr.fecha_emision) BETWEEN %s AND %s
                GROUP BY u.id_usuario
                ORDER BY monto_facturado DESC
            """, (fecha_desde, fecha_hasta))
            return cursor.fetchall()
        except Exception as e:
            logger.error("Error al generar resumen de liquidaciones: %s", e)
            return []
        finally:
            if conn:
                conn.close()
