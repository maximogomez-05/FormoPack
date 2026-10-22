"""Controlador de Logística — Flota, hojas de ruta, ruteo (RF 3.0 a RF 3.3)."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core.database import DatabaseManager
from app.models.vehiculo import Vehiculo
from app.models.hoja_ruta import HojaRuta
from app.services.ruteo import ServicioRuteo
from app.services.servicio_notificacion import notificar_cambio_estado_async
from app.utils.exceptions import (
    DatabaseConnectionError,
    DatabaseQueryError,
    ValidationError,
)
from config.settings import EstadosEnvio

logger = logging.getLogger(__name__)


class LogisticaController:
    """Gestiona flota, despacho y ruteo."""

    def __init__(self) -> None:
        self.db = DatabaseManager.get_instance()

    # ─────────────────────────────────────────
    # RF 3.1: Gestión de Flota
    # ─────────────────────────────────────────

    def listar_vehiculos(self) -> List[Dict[str, Any]]:
        """Lista todos los vehículos registrados."""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id_vehiculo, patente, capacidad_kg, estado
                FROM vehiculos
                ORDER BY patente ASC
            """)
            vehiculos = cursor.fetchall()
            return [Vehiculo.from_db_row(v).to_dict() for v in vehiculos]
        except Exception as e:
            logger.error("Error al listar vehículos: %s", e)
            raise DatabaseConnectionError(f"Error al listar vehículos: {e}")
        finally:
            if conn:
                conn.close()

    def obtener_vehiculo(self, id_vehiculo: int) -> Optional[Vehiculo]:
        """Obtiene un vehículo por ID."""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM vehiculos WHERE id_vehiculo = %s",
                (id_vehiculo,)
            )
            fila = cursor.fetchone()
            return Vehiculo.from_db_row(fila) if fila else None
        except Exception as e:
            logger.error("Error al obtener vehículo %d: %s", id_vehiculo, e)
            return None
        finally:
            if conn:
                conn.close()

    def registrar_vehiculo(self, patente: str, capacidad_kg: float) -> Vehiculo:
        """Registra un nuevo vehículo en la flota."""
        Vehiculo.validar_datos(patente, capacidad_kg)
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vehiculos (patente, capacidad_kg, estado) VALUES (%s, %s, 'disponible')",
                (patente.strip().upper(), float(capacidad_kg))
            )
            conn.commit()
            id_vehiculo = cursor.lastrowid
            logger.info("Vehículo registrado: %s (ID: %d)", patente, id_vehiculo)
            return Vehiculo(id_vehiculo, patente.upper(), capacidad_kg, "disponible")
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Error al registrar vehículo: %s", e)
            raise DatabaseQueryError(f"Error al registrar vehículo: {e}")
        finally:
            if conn:
                conn.close()

    # ─────────────────────────────────────────
    # RF 3.2: Armado de Despachos
    # ─────────────────────────────────────────

    def crear_hoja_ruta(
        self,
        nro_despacho: str,
        id_chofer: int,
        id_vehiculo: int,
        envios_ids: List[int],
    ) -> HojaRuta:
        """Crea una nueva hoja de ruta y asigna envíos."""
        if not nro_despacho.strip() or not envios_ids:
            raise ValidationError(field="hoja_ruta", reason="El despacho y al menos un envío son obligatorios")

        conn = None
        cursor = None
        id_hoja_ruta = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT capacidad_kg, estado FROM vehiculos WHERE id_vehiculo = %s FOR UPDATE",
                (id_vehiculo,),
            )
            vehiculo = cursor.fetchone()
            if not vehiculo or vehiculo["estado"] != "disponible":
                raise ValidationError(field="vehiculo", reason="El vehículo no existe o no está disponible")

            cursor.execute(
                "SELECT id_usuario FROM usuarios WHERE id_usuario = %s AND tipo_usuario = 'chofer' AND activo = 1",
                (id_chofer,),
            )
            if not cursor.fetchone():
                raise ValidationError(field="chofer", reason="El chofer no existe o no está activo")

            placeholders = ",".join(["%s"] * len(envios_ids))
            cursor.execute(
                f"""SELECT COUNT(DISTINCT e.id_envio) AS cantidad,
                           COALESCE(SUM(b.peso_real), 0) AS peso_total
                    FROM envios e
                    LEFT JOIN bultos b ON b.id_envio = e.id_envio
                    WHERE e.id_envio IN ({placeholders})
                      AND e.estado_actual = 'recibido'
                      AND e.id_hoja_ruta IS NULL""",
                envios_ids,
            )
            carga = cursor.fetchone()
            if carga["cantidad"] != len(set(envios_ids)):
                raise ValidationError(field="envios", reason="Solo se pueden asignar envíos recibidos y sin despacho")
            if float(carga["peso_total"]) > float(vehiculo["capacidad_kg"]):
                raise ValidationError(field="vehiculo", reason="La carga supera la capacidad del vehículo")

            # Crear hoja de ruta
            cursor.execute(
                """INSERT INTO hojas_de_ruta (nro_despacho, id_chofer, id_vehiculo)
                   VALUES (%s, %s, %s)""",
                (nro_despacho, id_chofer, id_vehiculo)
            )
            id_hoja_ruta = cursor.lastrowid

            # Asignar envíos a la hoja de ruta y cambiar estado
            for id_envio in envios_ids:
                cursor.execute(
                    "UPDATE envios SET id_hoja_ruta = %s, estado_actual = 'en_planta' WHERE id_envio = %s",
                    (id_hoja_ruta, id_envio)
                )
                cursor.execute(
                    """INSERT INTO historial_estados (id_envio, estado, ubicacion, observacion)
                       VALUES (%s, %s, %s, %s)""",
                    (id_envio, EstadosEnvio.EN_PLANTA, "Sucursal Origen", "Envío asignado a una hoja de ruta."),
                )
            cursor.execute(
                "UPDATE vehiculos SET estado = 'en_ruta' WHERE id_vehiculo = %s",
                (id_vehiculo,),
            )

            conn.commit()

        except ValidationError:
            if conn:
                try: conn.rollback()
                except Exception: pass
            raise
        except Exception as e:
            if conn:
                try: conn.rollback()
                except Exception: pass
            logger.error("Error al crear hoja de ruta: %s", e)
            raise DatabaseQueryError(f"Error al crear hoja de ruta: {e}") from e
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

        # Notificaciones asíncronas desacopladas (RF 5.4 / RF 6.2)
        for id_envio in envios_ids:
            notificar_cambio_estado_async(
                id_envio,
                nuevo_estado=EstadosEnvio.EN_PLANTA,
                observacion="El envío ha sido asignado a una hoja de ruta.",
            )

        # Recuperar la hoja completa con conexión independiente
        return self.obtener_hoja_ruta(id_hoja_ruta)

    def obtener_hoja_ruta(self, id_hoja_ruta: int) -> Optional[HojaRuta]:
        """Obtiene una hoja de ruta con sus envíos."""
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Hoja de ruta
            cursor.execute(
                "SELECT * FROM hojas_de_ruta WHERE id_hoja_ruta = %s",
                (id_hoja_ruta,)
            )
            hoja_row = cursor.fetchone()

            if not hoja_row:
                return None

            # Envíos asignados
            cursor.execute(
                """SELECT e.id_envio, e.nro_guia, e.estado_actual,
                          l.distancia_km, l.nombre as localidad_destino
                   FROM envios e
                   JOIN localidades l ON e.id_localidad_destino = l.id_localidad
                   WHERE e.id_hoja_ruta = %s
                   ORDER BY l.distancia_km ASC""",
                (id_hoja_ruta,)
            )
            envios = cursor.fetchall()

            return HojaRuta(
                id_hoja_ruta=hoja_row["id_hoja_ruta"],
                nro_despacho=hoja_row["nro_despacho"],
                id_chofer=hoja_row["id_chofer"],
                id_vehiculo=hoja_row["id_vehiculo"],
                fecha_emision=hoja_row.get("fecha_emision"),
                envios=envios or []
            )

        except Exception as e:
            logger.error("Error al obtener hoja de ruta %d: %s", id_hoja_ruta, e)
            return None
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def listar_hojas_ruta(self, limite: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lista todas las hojas de ruta con soporte de paginación."""
        conn = None
        cursor = None
        limite_seguro = max(1, min(limite, 500))
        offset_seguro = max(0, offset)
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    hr.id_hoja_ruta,
                    hr.nro_despacho,
                    hr.fecha_emision,
                    u.nombre as chofer_nombre,
                    v.patente,
                    COUNT(e.id_envio) as cantidad_envios,
                    COALESCE(MAX(l.distancia_km), 0) as max_distancia
                FROM hojas_de_ruta hr
                JOIN usuarios u ON hr.id_chofer = u.id_usuario
                JOIN vehiculos v ON hr.id_vehiculo = v.id_vehiculo
                LEFT JOIN envios e ON hr.id_hoja_ruta = e.id_hoja_ruta
                LEFT JOIN localidades l ON e.id_localidad_destino = l.id_localidad
                GROUP BY hr.id_hoja_ruta
                ORDER BY hr.fecha_emision DESC
                LIMIT %s OFFSET %s
            """, (limite_seguro, offset_seguro))
            return cursor.fetchall()
        except Exception as e:
            logger.error("Error al listar hojas de ruta: %s", e)
            raise DatabaseConnectionError(f"Error al listar hojas de ruta: {e}") from e
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def obtener_envios_mapa(self, limite: int = 250) -> List[Dict[str, Any]]:
        """Obtiene los envíos y su última ubicación para el mapa con límite de seguridad."""
        conn = None
        cursor = None
        limite_seguro = max(1, min(limite, 1000))
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT e.id_envio, e.nro_guia, e.estado_actual, e.id_hoja_ruta,
                       e.direccion_destino, e.fecha_creacion,
                       l.nombre AS localidad_destino, l.distancia_km,
                       hr.nro_despacho, u.nombre AS chofer_nombre, v.patente,
                       ug.latitud AS gps_latitud, ug.longitud AS gps_longitud,
                       ug.precision_m AS gps_precision_m,
                       ug.fecha_actualizacion AS gps_fecha,
                       ie.coordenadas_gps AS gps_entrega,
                       ie.fecha_hora AS gps_entrega_fecha
                FROM envios e
                JOIN localidades l ON l.id_localidad = e.id_localidad_destino
                LEFT JOIN hojas_de_ruta hr ON hr.id_hoja_ruta = e.id_hoja_ruta
                LEFT JOIN usuarios u ON u.id_usuario = hr.id_chofer
                LEFT JOIN vehiculos v ON v.id_vehiculo = hr.id_vehiculo
                LEFT JOIN ubicaciones_hojas_ruta ug
                    ON ug.id_hoja_ruta = e.id_hoja_ruta
                   AND e.estado_actual = 'en_ruta'
                   AND ug.fecha_actualizacion >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                LEFT JOIN intentos_entrega ie ON ie.id_intento = (
                    SELECT MAX(i.id_intento)
                    FROM intentos_entrega i
                    WHERE i.id_envio = e.id_envio
                      AND i.coordenadas_gps IS NOT NULL
                      AND e.estado_actual IN ('entregado', 'fallido', 'devolucion')
                )
                ORDER BY e.fecha_creacion DESC, e.id_envio DESC
                LIMIT %s
            """, (limite_seguro,))
            filas = cursor.fetchall()
            resultado = []
            for fila in filas:
                gps_latitud = fila.get("gps_latitud")
                gps_longitud = fila.get("gps_longitud")
                gps_fecha = fila.get("gps_fecha")
                gps_precision = fila.get("gps_precision_m")
                gps_en_vivo = gps_latitud is not None and gps_longitud is not None

                if not gps_en_vivo and fila.get("gps_entrega"):
                    try:
                        gps_latitud, gps_longitud = (
                            float(valor.strip())
                            for valor in fila["gps_entrega"].split(",", 1)
                        )
                        if not -90 <= gps_latitud <= 90 or not -180 <= gps_longitud <= 180:
                            gps_latitud = gps_longitud = None
                        else:
                            gps_fecha = fila.get("gps_entrega_fecha")
                    except (AttributeError, TypeError, ValueError):
                        gps_latitud = gps_longitud = None

                resultado.append({
                    "id_envio": fila["id_envio"],
                    "nro_guia": fila["nro_guia"],
                    "estado_actual": fila["estado_actual"],
                    "id_hoja_ruta": fila.get("id_hoja_ruta"),
                    "direccion_destino": fila.get("direccion_destino") or "",
                    "localidad_destino": fila["localidad_destino"],
                    "distancia_km": float(fila.get("distancia_km") or 0),
                    "nro_despacho": fila.get("nro_despacho"),
                    "chofer_nombre": fila.get("chofer_nombre"),
                    "patente": fila.get("patente"),
                    "gps_latitud": float(gps_latitud) if gps_latitud is not None else None,
                    "gps_longitud": float(gps_longitud) if gps_longitud is not None else None,
                    "gps_precision_m": float(gps_precision) if gps_en_vivo and gps_precision is not None else None,
                    "gps_fecha": gps_fecha.isoformat() if hasattr(gps_fecha, "isoformat") else str(gps_fecha) if gps_fecha else None,
                    "gps_en_vivo": gps_en_vivo,
                })
            return resultado
        except Exception as e:
            logger.error("Error al obtener envíos para mapa global: %s", e)
            raise DatabaseQueryError(f"Error al obtener envíos para mapa: {e}") from e
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    # ─────────────────────────────────────────
    # RF 3.3: Ruteo por Kilometraje
    # ─────────────────────────────────────────

    @staticmethod
    def es_envio_despachable(estado_actual: Optional[str], id_hoja_ruta: Any) -> bool:
        """Define si un envío aún puede entrar en una hoja de ruta."""
        if id_hoja_ruta is not None:
            return False

        estado = (estado_actual or "").strip().lower()
        return estado in {EstadosEnvio.RECIBIDO, EstadosEnvio.EN_PLANTA}

    def obtener_entregas_pendientes(
        self,
        estado: str = EstadosEnvio.RECIBIDO,
        limite: int = 150,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Obtiene solo envíos no resueltos y sin hoja de ruta asignada con paginación."""
        conn = None
        cursor = None
        limite_seguro = max(1, min(limite, 500))
        offset_seguro = max(0, offset)
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    e.id_envio,
                    e.nro_guia,
                    e.estado_actual,
                    l.id_localidad,
                    l.nombre as localidad_destino,
                    l.distancia_km,
                    SUM(b.peso_real) as peso_total_kg
                FROM envios e
                JOIN localidades l ON e.id_localidad_destino = l.id_localidad
                LEFT JOIN bultos b ON e.id_envio = b.id_envio
                WHERE e.estado_actual IN (%s, %s)
                  AND e.id_hoja_ruta IS NULL
                  AND e.estado_actual NOT IN ('entregado', 'fallido', 'devolucion', 'siniestro')
                GROUP BY e.id_envio
                ORDER BY l.distancia_km ASC
                LIMIT %s OFFSET %s
            """, (EstadosEnvio.RECIBIDO, EstadosEnvio.EN_PLANTA, limite_seguro, offset_seguro))
            return cursor.fetchall()
        except Exception as e:
            logger.error("Error al obtener entregas pendientes: %s", e)
            raise DatabaseConnectionError(f"Error al obtener entregas: {e}") from e
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    def sugerir_ruta_optima(self, entregas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ordena entregas por distancia para la ruta más eficiente."""
        return ServicioRuteo.ordenar_envios_por_distancia(entregas)

    def calcular_carga_total(self, envios_ids: List[int]) -> float:
        """Calcula el peso total de un grupo de envíos."""
        if not envios_ids:
            return 0.0
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            placeholders = ",".join(["%s"] * len(envios_ids))
            cursor.execute(f"""
                SELECT COALESCE(SUM(b.peso_real), 0) as peso_total
                FROM bultos b
                WHERE b.id_envio IN ({placeholders})
            """, envios_ids)
            resultado = cursor.fetchone()
            return float(resultado.get("peso_total", 0)) if resultado else 0.0
        except Exception as e:
            logger.error("Error al calcular carga: %s", e)
            return 0.0
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass
