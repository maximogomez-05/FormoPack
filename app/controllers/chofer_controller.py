"""Operaciones del chofer y prueba de entrega (RF 4.1 y RF 4.2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.database import DatabaseManager
from app.services.operaciones_logisticas import OperacionesLogisticas
from app.utils.exceptions import DatabaseQueryError, ValidationError

logger = logging.getLogger(__name__)


class ChoferController:
    """Consulta rutas propias y registra evidencias de entrega."""

    ESTADOS_ENTREGA = {"en_ruta", "fallido"}
    ESTADOS_FINALES = {"entregado", "devolucion", "siniestro"}

    @staticmethod
    def calcular_estado_post_intento(tipo_intento: str) -> str:
        """Devuelve el estado resultante del intento de entrega."""
        return "entregado" if tipo_intento == "entregado" else "fallido"

    @staticmethod
    def es_estado_terminal(estado: str | None) -> bool:
        """Indica si un envío ya no acepta más intentos de entrega."""
        return bool(estado) and estado in ChoferController.ESTADOS_FINALES

    @classmethod
    def es_hoja_ruta_completada(cls, estados: list[str]) -> bool:
        """Una hoja se completa cuando todos sus envíos alcanzan un estado final."""
        return bool(estados) and all(cls.es_estado_terminal(estado) for estado in estados)

    def __init__(self, db_manager=None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def _tiene_columna_estado(self):
        return True  # El esquema requerido se aplica mediante migraciones, no durante una petición.

    def obtener_panel(self, id_chofer):
        conn, cursor = None, None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""SELECT h.id_hoja_ruta,h.nro_despacho,h.fecha_emision,h.fecha_inicio,h.estado,
                v.patente,v.capacidad_kg FROM hojas_de_ruta h JOIN vehiculos v ON v.id_vehiculo=h.id_vehiculo
                WHERE h.id_chofer=%s AND h.estado='abierta' ORDER BY h.fecha_emision,h.id_hoja_ruta""", (id_chofer,))
            hojas = cursor.fetchall()
            for hoja in hojas:
                cursor.execute("""SELECT e.id_envio,e.nro_guia,COALESCE(a.resolucion,e.estado_actual) AS estado_actual,
                    e.direccion_destino,l.nombre AS localidad_destino,l.distancia_km,a.resolucion,
                    i.tipo_intento,i.fecha_hora AS intento_fecha,i.motivo_fallo AS ultimo_motivo_fallo,
                    (SELECT COUNT(*) FROM intentos_entrega j WHERE j.id_envio=e.id_envio) AS cantidad_intentos
                    FROM hojas_ruta_envios a JOIN envios e ON e.id_envio=a.id_envio
                    JOIN localidades l ON l.id_localidad=e.id_localidad_destino
                    LEFT JOIN intentos_entrega i ON i.id_intento=(SELECT MAX(j.id_intento) FROM intentos_entrega j WHERE j.id_envio=e.id_envio AND j.id_hoja_ruta=a.id_hoja_ruta)
                    WHERE a.id_hoja_ruta=%s ORDER BY l.distancia_km,e.nro_guia""", (hoja["id_hoja_ruta"],))
                hoja["envios"] = cursor.fetchall()
            return {"hojas": hojas}
        except Exception as exc:
            raise DatabaseQueryError("No se pudieron consultar las rutas. Intentá nuevamente.") from exc
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def iniciar_hoja(self, id_chofer, id_hoja_ruta):
        return OperacionesLogisticas(self.db).iniciar(id_chofer, id_hoja_ruta)

    def actualizar_ubicacion_ruta(
        self,
        id_chofer: int,
        id_hoja_ruta: int,
        latitud: float,
        longitud: float,
        precision_m: float | None,
    ) -> None:
        """Guarda el último punto GPS de una hoja activa del chofer autenticado."""
        if not -90 <= latitud <= 90 or not -180 <= longitud <= 180:
            raise ValidationError(field="ubicacion", reason="Las coordenadas GPS están fuera de rango")

        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """SELECT hr.id_hoja_ruta
                   FROM hojas_de_ruta hr
                   WHERE hr.id_hoja_ruta = %s AND hr.id_chofer = %s AND hr.estado='abierta' AND hr.fecha_inicio IS NOT NULL
                     AND EXISTS (
                         SELECT 1 FROM envios e
                         WHERE e.id_hoja_ruta = hr.id_hoja_ruta
                           AND e.estado_actual = 'en_ruta'
                     )""",
                (id_hoja_ruta, id_chofer),
            )
            if not cursor.fetchone():
                raise ValidationError(field="hoja_ruta", reason="La ruta no está activa o no pertenece al chofer actual")

            cursor.execute(
                """INSERT INTO ubicaciones_hojas_ruta
                       (id_hoja_ruta, id_chofer, latitud, longitud, precision_m, fecha_actualizacion)
                   VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                   ON DUPLICATE KEY UPDATE
                       id_chofer = %s, latitud = %s, longitud = %s,
                       precision_m = %s, fecha_actualizacion = CURRENT_TIMESTAMP""",
                (
                    id_hoja_ruta, id_chofer, latitud, longitud, precision_m,
                    id_chofer, latitud, longitud, precision_m,
                ),
            )
            conn.commit()
        except ValidationError:
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.exception("Error al actualizar ubicación GPS de ruta: %s", exc)
            raise DatabaseQueryError("No se pudo actualizar la ubicación de la ruta.") from exc
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def registrar_entrega(self, id_chofer, id_hoja_ruta, id_envio, tipo_intento, dni_receptor=None,
                          firma_receptor=None, foto_remito=None, coordenadas_gps=None, motivo_fallo=None):
        return OperacionesLogisticas(self.db).entregar(id_chofer, id_hoja_ruta, id_envio, tipo_intento,
            dni_receptor, firma_receptor, foto_remito, coordenadas_gps, motivo_fallo)

    def registrar_devolucion(self, id_chofer, id_hoja_ruta, id_envio, motivo):
        raise ValidationError("devolucion", "El resultado de visita queda registrado. Administración gestiona el retorno desde depósito")

    @staticmethod
    def validar_foto(nombre: str | None, permitido: set[str]) -> bool:
        """Valida la extensión de una foto antes de guardarla."""
        if not nombre:
            return False
        return Path(nombre).suffix.lower() in permitido
