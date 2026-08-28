"""Controlador de Turnos de Caja — RF 2.6."""

import logging
from typing import Optional
from datetime import datetime

from app.core.database import DatabaseManager
from app.models.turno_caja import TurnoCaja
from app.utils.exceptions import (
    DatabaseQueryError,
    TurnoCajaError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class CajaController:
    """Controlador para la gestión de turnos de caja.

    Cubre RF 2.6: Conciliación de Caja (Efectivo y Virtual).
    Discrimina automáticamente los ingresos físicos (Efectivo) de los
    ingresos digitales (MercadoPago/Transferencias).
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self._db = db_manager or DatabaseManager.get_instance()

    def abrir_turno(self, id_recepcionista: int, saldo_inicial: float = 0.0) -> TurnoCaja:
        """Abre un nuevo turno de caja para una recepcionista.

        Args:
            id_recepcionista: ID del usuario recepcionista.
            saldo_inicial: Saldo inicial en efectivo de la caja.

        Returns:
            Instancia de TurnoCaja creada.

        Raises:
            TurnoCajaError: Si la recepcionista ya tiene un turno abierto.
        """
        # Verificar que no tenga un turno abierto
        turno_abierto = self._obtener_turno_abierto(id_recepcionista)
        if turno_abierto:
            raise TurnoCajaError(
                f"La recepcionista #{id_recepcionista} ya tiene un turno abierto (#{turno_abierto.id_turno})."
            )

        sql = """
            INSERT INTO turnos_caja (id_recepcionista, saldo_inicial, estado_caja)
            VALUES (%s, %s, 'abierto')
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (id_recepcionista, saldo_inicial))
            conn.commit()
            id_turno = cursor.lastrowid
            cursor.close()

            turno = TurnoCaja(
                id_turno=id_turno,
                id_recepcionista=id_recepcionista,
                saldo_inicial=saldo_inicial,
            )
            logger.info("Turno de caja #%d abierto por recepcionista #%d", id_turno, id_recepcionista)
            return turno

        except TurnoCajaError:
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseQueryError(f"Error al abrir turno de caja: {e}") from e
        finally:
            if conn:
                conn.close()

    def cerrar_turno(self, id_turno: int) -> dict:
        """Cierra un turno de caja y genera el resumen de conciliación.

        Args:
            id_turno: ID del turno a cerrar.

        Returns:
            Diccionario con el resumen del cierre de caja.

        Raises:
            TurnoCajaError: Si el turno no existe o ya está cerrado.
        """
        turno = self._obtener_turno_por_id(id_turno)
        if not turno:
            raise TurnoCajaError(f"Turno de caja #{id_turno} no encontrado.")
        if turno.estado_caja == "cerrado":
            raise TurnoCajaError(f"El turno #{id_turno} ya esta cerrado.")

        # Obtener totales reales de la BD
        totales = self._calcular_totales_turno(id_turno)

        sql = """
            UPDATE turnos_caja
            SET estado_caja = 'cerrado',
                fecha_cierre = NOW(),
                ingresos_efectivo = %s,
                ingresos_digitales = %s
            WHERE id_turno = %s
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (
                totales["total_efectivo"],
                totales["total_digital"],
                id_turno,
            ))
            conn.commit()
            cursor.close()

            resumen = {
                "id_turno": id_turno,
                "fecha_cierre": datetime.now().isoformat(),
                "saldo_inicial": turno.saldo_inicial,
                "ingresos_efectivo": totales["total_efectivo"],
                "ingresos_digitales": totales["total_digital"],
                "total_caja_fisica": round(turno.saldo_inicial + totales["total_efectivo"], 2),
                "total_ingresos": round(totales["total_efectivo"] + totales["total_digital"], 2),
                "cantidad_operaciones": totales["cantidad_pagos"],
            }

            logger.info("Turno #%d cerrado. Resumen: %s", id_turno, resumen)
            return resumen

        except TurnoCajaError:
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseQueryError(f"Error al cerrar turno: {e}") from e
        finally:
            if conn:
                conn.close()

    def obtener_resumen(self, id_turno: int) -> dict:
        """Obtiene el resumen actual de un turno de caja (abierto o cerrado).

        Args:
            id_turno: ID del turno.

        Returns:
            Diccionario con el estado actual de la caja.
        """
        turno = self._obtener_turno_por_id(id_turno)
        if not turno:
            raise TurnoCajaError(f"Turno de caja #{id_turno} no encontrado.")

        totales = self._calcular_totales_turno(id_turno)

        return {
            "id_turno": turno.id_turno,
            "id_recepcionista": turno.id_recepcionista,
            "estado_caja": turno.estado_caja,
            "fecha_apertura": turno.fecha_apertura.isoformat() if turno.fecha_apertura else None,
            "saldo_inicial": turno.saldo_inicial,
            "ingresos_efectivo": totales["total_efectivo"],
            "ingresos_digitales": totales["total_digital"],
            "total_caja_fisica": round(turno.saldo_inicial + totales["total_efectivo"], 2),
            "total_ingresos": round(totales["total_efectivo"] + totales["total_digital"], 2),
            "cantidad_operaciones": totales["cantidad_pagos"],
        }

    # --- Métodos internos ---

    def _obtener_turno_abierto(self, id_recepcionista: int) -> Optional[TurnoCaja]:
        """Busca si la recepcionista tiene un turno abierto."""
        sql = """
            SELECT * FROM turnos_caja
            WHERE id_recepcionista = %s AND estado_caja = 'abierto'
            LIMIT 1
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (id_recepcionista,))
            fila = cursor.fetchone()
            cursor.close()
            return TurnoCaja.from_db_row(fila) if fila else None
        except Exception as e:
            raise DatabaseQueryError(f"Error al buscar turno abierto: {e}") from e
        finally:
            if conn:
                conn.close()

    def _obtener_turno_por_id(self, id_turno: int) -> Optional[TurnoCaja]:
        """Obtiene un turno de caja por su ID."""
        sql = "SELECT * FROM turnos_caja WHERE id_turno = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (id_turno,))
            fila = cursor.fetchone()
            cursor.close()
            return TurnoCaja.from_db_row(fila) if fila else None
        except Exception as e:
            raise DatabaseQueryError(f"Error al obtener turno: {e}") from e
        finally:
            if conn:
                conn.close()

    def _calcular_totales_turno(self, id_turno: int) -> dict:
        """Calcula los totales de pagos registrados en un turno."""
        sql = """
            SELECT
                COALESCE(SUM(CASE WHEN tipo_pago = 'efectivo' THEN monto ELSE 0 END), 0) AS total_efectivo,
                COALESCE(SUM(CASE WHEN tipo_pago = 'digital' THEN monto ELSE 0 END), 0) AS total_digital,
                COUNT(*) AS cantidad_pagos
            FROM pagos
            WHERE id_turno = %s
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (id_turno,))
            fila = cursor.fetchone()
            cursor.close()
            return {
                "total_efectivo": float(fila["total_efectivo"]) if fila else 0.0,
                "total_digital": float(fila["total_digital"]) if fila else 0.0,
                "cantidad_pagos": int(fila["cantidad_pagos"]) if fila else 0,
            }
        except Exception as e:
            raise DatabaseQueryError(f"Error al calcular totales: {e}") from e
        finally:
            if conn:
                conn.close()
