"""Controlador de Logística — Flota, hojas de ruta, ruteo (RF 3.0 a RF 3.3)."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core.database import DatabaseManager
from app.models.vehiculo import Vehiculo
from app.models.hoja_ruta import HojaRuta
from app.services.ruteo import ServicioRuteo
from app.utils.exceptions import (
    DatabaseConnectionError,
    DatabaseQueryError,
    ValidationError,
)

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
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id_vehiculo, patente, capacidad_kg, estado
                FROM vehiculos
                ORDER BY patente ASC
            """)
            vehiculos = cursor.fetchall()
            cursor.close()
            conn.close()
            return [Vehiculo.from_db_row(v).to_dict() for v in vehiculos]
        except Exception as e:
            logger.error("Error al listar vehículos: %s", e)
            raise DatabaseConnectionError(f"Error al listar vehículos: {e}")

    def obtener_vehiculo(self, id_vehiculo: int) -> Optional[Vehiculo]:
        """Obtiene un vehículo por ID."""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM vehiculos WHERE id_vehiculo = %s",
                (id_vehiculo,)
            )
            fila = cursor.fetchone()
            cursor.close()
            conn.close()
            return Vehiculo.from_db_row(fila) if fila else None
        except Exception as e:
            logger.error("Error al obtener vehículo %d: %s", id_vehiculo, e)
            return None

    def registrar_vehiculo(self, patente: str, capacidad_kg: float) -> Vehiculo:
        """Registra un nuevo vehículo en la flota."""
        Vehiculo.validar_datos(patente, capacidad_kg)
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vehiculos (patente, capacidad_kg, estado) VALUES (%s, %s, 'disponible')",
                (patente.strip().upper(), float(capacidad_kg))
            )
            conn.commit()
            id_vehiculo = cursor.lastrowid
            cursor.close()
            conn.close()
            logger.info("Vehículo registrado: %s (ID: %d)", patente, id_vehiculo)
            return Vehiculo(id_vehiculo, patente.upper(), capacidad_kg, "disponible")
        except Exception as e:
            logger.error("Error al registrar vehículo: %s", e)
            raise DatabaseQueryError(f"Error al registrar vehículo: {e}")

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
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)

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

            conn.commit()
            cursor.close()

            # Recuperar la hoja completa
            return self.obtener_hoja_ruta(id_hoja_ruta)

        except Exception as e:
            logger.error("Error al crear hoja de ruta: %s", e)
            raise DatabaseQueryError(f"Error al crear hoja de ruta: {e}")

    def obtener_hoja_ruta(self, id_hoja_ruta: int) -> Optional[HojaRuta]:
        """Obtiene una hoja de ruta con sus envíos."""
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
                cursor.close()
                conn.close()
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

            cursor.close()
            conn.close()

            hoja = HojaRuta(
                id_hoja_ruta=hoja_row["id_hoja_ruta"],
                nro_despacho=hoja_row["nro_despacho"],
                id_chofer=hoja_row["id_chofer"],
                id_vehiculo=hoja_row["id_vehiculo"],
                fecha_emision=hoja_row.get("fecha_emision"),
                envios=envios or []
            )
            return hoja

        except Exception as e:
            logger.error("Error al obtener hoja de ruta %d: %s", id_hoja_ruta, e)
            return None

    def listar_hojas_ruta(self) -> List[Dict[str, Any]]:
        """Lista todas las hojas de ruta activas."""
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
                LIMIT 50
            """)
            hojas = cursor.fetchall()
            cursor.close()
            conn.close()
            return hojas
        except Exception as e:
            logger.error("Error al listar hojas de ruta: %s", e)
            raise DatabaseConnectionError(f"Error al listar hojas de ruta: {e}")

    # ─────────────────────────────────────────
    # RF 3.3: Ruteo por Kilometraje
    # ─────────────────────────────────────────

    def obtener_entregas_pendientes(self, estado: str = "recibido") -> List[Dict[str, Any]]:
        """Obtiene envíos en estado 'recibido' listos para despachar."""
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
                WHERE e.estado_actual = %s AND e.id_hoja_ruta IS NULL
                GROUP BY e.id_envio
                ORDER BY l.distancia_km ASC
            """, (estado,))
            entregas = cursor.fetchall()
            cursor.close()
            conn.close()
            return entregas
        except Exception as e:
            logger.error("Error al obtener entregas pendientes: %s", e)
            raise DatabaseConnectionError(f"Error al obtener entregas: {e}")

    def sugerir_ruta_optima(self, entregas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ordena entregas por distancia para la ruta más eficiente."""
        return ServicioRuteo.ordenar_envios_por_distancia(entregas)

    def calcular_carga_total(self, envios_ids: List[int]) -> float:
        """Calcula el peso total de un grupo de envíos."""
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
            cursor.close()
            conn.close()
            return float(resultado.get("peso_total", 0))
        except Exception as e:
            logger.error("Error al calcular carga: %s", e)
            return 0.0
