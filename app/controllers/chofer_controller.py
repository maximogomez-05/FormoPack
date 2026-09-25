"""Operaciones del chofer y prueba de entrega (RF 4.1 y RF 4.2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.database import DatabaseManager
from app.utils.exceptions import DatabaseQueryError, ValidationError

logger = logging.getLogger(__name__)


class ChoferController:
    """Consulta rutas propias y registra evidencias de entrega."""

    ESTADOS_ENTREGA = {"recibido", "en_planta", "en_ruta", "fallido", "devolucion"}

    @staticmethod
    def calcular_estado_post_intento(tipo_intento: str) -> str:
        """Devuelve el estado resultante del intento de entrega."""
        return "entregado" if tipo_intento == "entregado" else "fallido"

    @staticmethod
    def es_estado_terminal(estado: str | None) -> bool:
        """Indica si un envío ya no acepta más intentos de entrega."""
        return bool(estado) and estado in {"entregado", "fallido", "devolucion"}

    def __init__(self) -> None:
        self.db = DatabaseManager.get_instance()

    def obtener_panel(self, id_chofer: int) -> dict[str, Any]:
        """Devuelve hojas activas y sus envios para el chofer autenticado."""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT hr.id_hoja_ruta, hr.nro_despacho, hr.fecha_emision,
                          v.patente, v.capacidad_kg
                   FROM hojas_de_ruta hr
                   JOIN vehiculos v ON v.id_vehiculo = hr.id_vehiculo
                   WHERE hr.id_chofer = %s
                   ORDER BY hr.fecha_emision DESC""",
                (id_chofer,),
            )
            hojas = cursor.fetchall()
            for hoja in hojas:
                cursor.execute(
                    """SELECT e.id_envio, e.nro_guia, e.estado_actual,
                              e.direccion_destino, l.nombre AS localidad_destino,
                              l.distancia_km, i.tipo_intento, i.fecha_hora AS intento_fecha
                       FROM envios e
                       JOIN localidades l ON l.id_localidad = e.id_localidad_destino
                       LEFT JOIN intentos_entrega i ON i.id_intento = (
                           SELECT MAX(i2.id_intento) FROM intentos_entrega i2
                           WHERE i2.id_envio = e.id_envio
                       )
                       WHERE e.id_hoja_ruta = %s
                       ORDER BY l.distancia_km ASC, e.nro_guia ASC""",
                    (hoja["id_hoja_ruta"],),
                )
                hoja["envios"] = cursor.fetchall()
            return {"hojas": hojas}
        finally:
            cursor.close()
            conn.close()

    def iniciar_hoja(self, id_chofer: int, id_hoja_ruta: int) -> None:
        """Pone la hoja en ruta y registra el cambio para cada envio."""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id_hoja_ruta FROM hojas_de_ruta WHERE id_hoja_ruta = %s AND id_chofer = %s",
                (id_hoja_ruta, id_chofer),
            )
            if not cursor.fetchone():
                raise ValidationError(field="hoja_ruta", reason="La hoja no pertenece al chofer actual")

            cursor.execute(
                "SELECT id_envio FROM envios WHERE id_hoja_ruta = %s AND estado_actual IN ('en_planta', 'recibido')",
                (id_hoja_ruta,),
            )
            envios = cursor.fetchall()
            if not envios:
                raise ValidationError(field="hoja_ruta", reason="La hoja no tiene envios pendientes")

            cursor.execute(
                "UPDATE envios SET estado_actual = 'en_ruta' WHERE id_hoja_ruta = %s AND estado_actual IN ('en_planta', 'recibido')",
                (id_hoja_ruta,),
            )
            for envio in envios:
                cursor.execute(
                    "INSERT INTO historial_estados (id_envio, estado, ubicacion, observacion) VALUES (%s, 'en_ruta', %s, %s)",
                    (envio["id_envio"], "En ruta", "Ruta iniciada por el chofer"),
                )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            logger.exception("Error al iniciar hoja de ruta")
            raise DatabaseQueryError(f"No se pudo iniciar la hoja de ruta: {exc}") from exc
        finally:
            cursor.close()
            conn.close()

    def registrar_entrega(
        self,
        id_chofer: int,
        id_hoja_ruta: int,
        id_envio: int,
        tipo_intento: str,
        dni_receptor: str | None,
        firma_receptor: str | None,
        foto_remito: str | None,
        coordenadas_gps: str | None,
        motivo_fallo: str | None,
    ) -> None:
        """Guarda un POD solo si el envio pertenece a una hoja del chofer."""
        if tipo_intento not in {"entregado", "fallido"}:
            raise ValidationError(field="tipo_intento", reason="El tipo de entrega no es válido")
        if tipo_intento == "entregado" and (not dni_receptor or not firma_receptor):
            raise ValidationError(field="evidencia", reason="Una entrega exitosa requiere DNI y firma")
        if tipo_intento == "fallido" and not motivo_fallo:
            raise ValidationError(field="motivo_fallo", reason="Una entrega fallida requiere un motivo")

        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT e.estado_actual FROM envios e
                   JOIN hojas_de_ruta hr ON hr.id_hoja_ruta = e.id_hoja_ruta
                   WHERE e.id_envio = %s AND e.id_hoja_ruta = %s AND hr.id_chofer = %s
                   FOR UPDATE""",
                (id_envio, id_hoja_ruta, id_chofer),
            )
            envio = cursor.fetchone()
            if not envio:
                raise ValidationError(field="envio", reason="El envío no pertenece a una hoja del chofer")
            if envio["estado_actual"] not in self.ESTADOS_ENTREGA:
                raise ValidationError(field="envio", reason="El envío ya no admite un intento de entrega")

            nuevo_estado = self.calcular_estado_post_intento(tipo_intento)
            cursor.execute(
                """INSERT INTO intentos_entrega
                   (id_envio, id_hoja_ruta, coordenadas_gps, tipo_intento,
                    dni_receptor, firma_receptor, foto_remito, motivo_fallo)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    id_envio, id_hoja_ruta, coordenadas_gps, tipo_intento,
                    dni_receptor, firma_receptor, foto_remito, motivo_fallo,
                ),
            )
            cursor.execute(
                "UPDATE envios SET estado_actual = %s WHERE id_envio = %s",
                (nuevo_estado, id_envio),
            )
            observacion = "Entrega confirmada por el chofer" if tipo_intento == "entregado" else f"Entrega fallida: {motivo_fallo}"
            cursor.execute(
                """INSERT INTO historial_estados
                   (id_envio, estado, ubicacion, observacion)
                   VALUES (%s, %s, %s, %s)""",
                (id_envio, nuevo_estado, coordenadas_gps or "Sin ubicación", observacion),
            )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            logger.exception("Error al registrar prueba de entrega")
            raise DatabaseQueryError(f"No se pudo registrar la entrega: {exc}") from exc
        finally:
            cursor.close()
            conn.close()

    def registrar_devolucion(self, id_chofer: int, id_hoja_ruta: int, id_envio: int, motivo: str) -> None:
        """Cambia un envío fallido a devolución y deja trazabilidad."""
        if not motivo or not motivo.strip():
            raise ValidationError(field="motivo_devolucion", reason="El motivo de devolución es obligatorio")

        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT e.estado_actual FROM envios e
                   JOIN hojas_de_ruta hr ON hr.id_hoja_ruta = e.id_hoja_ruta
                   WHERE e.id_envio = %s AND e.id_hoja_ruta = %s AND hr.id_chofer = %s
                   FOR UPDATE""",
                (id_envio, id_hoja_ruta, id_chofer),
            )
            envio = cursor.fetchone()
            if not envio:
                raise ValidationError(field="envio", reason="El envío no pertenece a una hoja del chofer")
            if envio["estado_actual"] != "fallido":
                raise ValidationError(field="envio", reason="Sólo se puede devolver un envío fallido")

            cursor.execute("UPDATE envios SET estado_actual = 'devolucion', es_devolucion = 1 WHERE id_envio = %s", (id_envio,))
            cursor.execute(
                """INSERT INTO historial_estados (id_envio, estado, ubicacion, observacion)
                   VALUES (%s, 'devolucion', 'Base operativa', %s)""",
                (id_envio, f"Devolución solicitada por el chofer: {motivo.strip()}"),
            )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            logger.exception("Error al registrar devolución")
            raise DatabaseQueryError(f"No se pudo registrar la devolución: {exc}") from exc
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def validar_foto(nombre: str | None, permitido: set[str]) -> bool:
        """Valida la extensión de una foto antes de guardarla."""
        if not nombre:
            return False
        return Path(nombre).suffix.lower() in permitido
