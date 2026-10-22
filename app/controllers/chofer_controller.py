"""Operaciones del chofer y prueba de entrega (RF 4.1 y RF 4.2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.database import DatabaseManager
from app.models.prueba_entrega import EntregaFallida, PruebaDeEntrega
from app.services.servicio_notificacion import notificar_cambio_estado_async
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

    _columna_estado_cache: Optional[bool] = None

    def __init__(self) -> None:
        self.db = DatabaseManager.get_instance()

    def _tiene_columna_estado(self) -> bool:
        """Compatibilidad con esquemas sin columna estado en hojas_de_ruta (con caché)."""
        if ChoferController._columna_estado_cache is not None:
            return ChoferController._columna_estado_cache
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW COLUMNS FROM hojas_de_ruta LIKE 'estado'")
            ChoferController._columna_estado_cache = (cursor.fetchone() is not None)
            return ChoferController._columna_estado_cache
        except Exception:
            return False
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def obtener_panel(self, id_chofer: int) -> dict[str, Any]:
        """Devuelve hojas activas y sus envíos para el chofer autenticado."""
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Consultas estáticas parametrizadas sin interpolación de cadenas
            if self._tiene_columna_estado():
                sql_hojas = """
                    SELECT hr.id_hoja_ruta, hr.nro_despacho, hr.fecha_emision,
                           v.patente, v.capacidad_kg
                    FROM hojas_de_ruta hr
                    JOIN vehiculos v ON v.id_vehiculo = hr.id_vehiculo
                    WHERE hr.id_chofer = %s
                      AND (hr.estado = 'abierta' OR hr.fecha_emision >= DATE_SUB(NOW(), INTERVAL 24 HOUR))
                    ORDER BY hr.fecha_emision DESC
                """
            else:
                sql_hojas = """
                    SELECT hr.id_hoja_ruta, hr.nro_despacho, hr.fecha_emision,
                           v.patente, v.capacidad_kg
                    FROM hojas_de_ruta hr
                    JOIN vehiculos v ON v.id_vehiculo = hr.id_vehiculo
                    WHERE hr.id_chofer = %s
                    ORDER BY hr.fecha_emision DESC
                """

            cursor.execute(sql_hojas, (id_chofer,))
            hojas = cursor.fetchall()

            if not hojas:
                return {"hojas": []}

            # Optimización N+1: Batch query para todos los envíos de las hojas activas
            placeholders = ",".join(["%s"] * len(hojas))
            ids_hojas = [h["id_hoja_ruta"] for h in hojas]
            cursor.execute(
                f"""SELECT e.id_hoja_ruta, e.id_envio, e.nro_guia, e.estado_actual,
                          e.direccion_destino, l.nombre AS localidad_destino,
                          l.distancia_km, i.tipo_intento, i.fecha_hora AS intento_fecha,
                          i.motivo_fallo AS ultimo_motivo_fallo,
                          (SELECT COUNT(*) FROM intentos_entrega total
                           WHERE total.id_envio = e.id_envio) AS cantidad_intentos
                   FROM envios e
                   JOIN localidades l ON l.id_localidad = e.id_localidad_destino
                   LEFT JOIN intentos_entrega i ON i.id_intento = (
                       SELECT MAX(i2.id_intento) FROM intentos_entrega i2
                       WHERE i2.id_envio = e.id_envio
                   )
                   WHERE e.id_hoja_ruta IN ({placeholders})
                   ORDER BY l.distancia_km ASC, e.nro_guia ASC""",
                tuple(ids_hojas),
            )
            envios_todos = cursor.fetchall()
            envios_por_hoja: dict[int, list[dict[str, Any]]] = {h_id: [] for h_id in ids_hojas}
            for e in envios_todos:
                h_id = e.get("id_hoja_ruta")
                if h_id in envios_por_hoja:
                    envios_por_hoja[h_id].append(e)

            for hoja in hojas:
                hoja["envios"] = envios_por_hoja.get(hoja["id_hoja_ruta"], [])
            return {"hojas": hojas}
        except ValidationError:
            raise
        except Exception as exc:
            logger.exception("Error al obtener panel del chofer: %s", exc)
            raise DatabaseQueryError("No se pudo obtener las hojas de ruta asignadas.") from exc
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def iniciar_hoja(self, id_chofer: int, id_hoja_ruta: int) -> None:
        """Pone la hoja en ruta y registra el cambio para cada envio."""
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

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

            # --- NOTIFICACIONES ASÍNCRONAS (RF 5.4 / RF 6.2) ---
            for envio in envios:
                notificar_cambio_estado_async(
                    envio["id_envio"],
                    nuevo_estado="en_ruta",
                    observacion="Ruta iniciada por el chofer.",
                )

        except ValidationError:
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.exception("Error al iniciar hoja de ruta: %s", exc)
            raise DatabaseQueryError("No se pudo iniciar la hoja de ruta.") from exc
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

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
                   WHERE hr.id_hoja_ruta = %s AND hr.id_chofer = %s
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
        if tipo_intento == "fallido":
            prueba = EntregaFallida(
                id_intento=None,
                id_envio=id_envio,
                id_hoja_ruta=id_hoja_ruta,
                motivo_fallo=motivo_fallo or "",
                dni_receptor=dni_receptor,
                firma_receptor=firma_receptor,
                foto_remito=foto_remito,
                coordenadas_gps=coordenadas_gps,
            )
        else:
            prueba = PruebaDeEntrega(
                id_intento=None,
                id_envio=id_envio,
                id_hoja_ruta=id_hoja_ruta,
                tipo_intento=tipo_intento,
                dni_receptor=dni_receptor,
                firma_receptor=firma_receptor,
                foto_remito=foto_remito,
                coordenadas_gps=coordenadas_gps,
                motivo_fallo=motivo_fallo,
            )

        prueba.validar_entrega()

        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

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
            if envio["estado_actual"] in ("en_planta", "recibido"):
                raise ValidationError(
                    field="envio",
                    reason="No podés registrar el resultado de entrega porque la ruta aún no ha sido iniciada. Primero iniciá la ruta."
                )
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
            self._liberar_vehiculo_si_hoja_completada(cursor, id_hoja_ruta)
            conn.commit()

            # --- NOTIFICACION ASÍNCRONA (RF 5.4 / RF 6.2) ---
            notificar_cambio_estado_async(
                id_envio,
                nuevo_estado=nuevo_estado,
                observacion=observacion,
            )

        except ValidationError:
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.exception("Error al registrar prueba de entrega: %s", exc)
            raise DatabaseQueryError("No se pudo registrar la entrega.") from exc
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def registrar_devolucion(self, id_chofer: int, id_hoja_ruta: int, id_envio: int, motivo: str) -> None:
        """Cambia un envío fallido a devolución y deja trazabilidad."""
        entrega_fallida = EntregaFallida(
            id_intento=None,
            id_envio=id_envio,
            id_hoja_ruta=id_hoja_ruta,
            motivo_fallo=motivo,
        )
        observacion_historial = entrega_fallida.procesar_retorno_devolucion()

        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

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
                (id_envio, observacion_historial),
            )
            self._liberar_vehiculo_si_hoja_completada(cursor, id_hoja_ruta)
            conn.commit()

            # --- NOTIFICACION ASÍNCRONA (RF 5.4 / RF 6.2) ---
            notificar_cambio_estado_async(
                id_envio,
                nuevo_estado="devolucion",
                observacion=observacion_historial,
            )

        except ValidationError:
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.exception("Error al registrar devolución: %s", exc)
            raise DatabaseQueryError("No se pudo registrar la devolución.") from exc
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def _liberar_vehiculo_si_hoja_completada(self, cursor, id_hoja_ruta: int) -> None:
        """RF 6.1: Cierra la hoja de ruta y libera el vehículo cuando todos los envíos finalizaron."""
        cursor.execute(
            "SELECT estado_actual FROM envios WHERE id_hoja_ruta = %s",
            (id_hoja_ruta,),
        )
        estados = [fila["estado_actual"] for fila in cursor.fetchall()]
        if self.es_hoja_ruta_completada(estados):
            # Marcar hoja como cerrada con timestamp si la columna existe en el esquema
            if self._tiene_columna_estado():
                cursor.execute(
                    "UPDATE hojas_de_ruta SET estado = 'cerrada', fecha_cierre = NOW() WHERE id_hoja_ruta = %s AND estado = 'abierta'",
                    (id_hoja_ruta,),
                )
            # Devolver el vehículo a disponible
            cursor.execute(
                """UPDATE vehiculos v
                   JOIN hojas_de_ruta hr ON hr.id_vehiculo = v.id_vehiculo
                   SET v.estado = 'disponible'
                   WHERE hr.id_hoja_ruta = %s AND v.estado = 'en_ruta'""",
                (id_hoja_ruta,),
            )
            logger.info("RF 6.1: Hoja de ruta %d cerrada automáticamente. Vehículo liberado.", id_hoja_ruta)

    @staticmethod
    def validar_foto(nombre: str | None, permitido: set[str]) -> bool:
        """Valida la extensión de una foto antes de guardarla."""
        if not nombre:
            return False
        return Path(nombre).suffix.lower() in permitido
