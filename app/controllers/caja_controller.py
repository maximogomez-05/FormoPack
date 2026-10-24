"""Controlador de Turnos de Caja — RF 2.6."""

import logging
from contextlib import contextmanager
from app.services.validacion_entrada import ValidacionEntrada as V
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

    @contextmanager
    def _transaccion(self):
        conn, cur = None, None
        try:
            conn = self._db.get_connection()
            cur = conn.cursor(dictionary=True)
            yield cur
            conn.commit()
        except (TurnoCajaError, ValidationError):
            if conn:
                conn.rollback()
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            raise DatabaseQueryError("No se pudo completar la operación de caja") from exc
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    @staticmethod
    def _operador(cur, id_usuario):
        cur.execute("SELECT activo, tipo_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (id_usuario,))
        usuario = cur.fetchone()
        if not usuario or not usuario["activo"] or usuario["tipo_usuario"] not in {"administrador", "recepcionista"}:
            raise TurnoCajaError("La cuenta no está habilitada para operar una caja.")

    def abrir_turno(self, id_recepcionista: int, saldo_inicial: float = 0.0) -> TurnoCaja:
        id_recepcionista = V.entero(id_recepcionista, "id_recepcionista")
        saldo_inicial = V.decimal(saldo_inicial, "saldo_inicial")
        with self._transaccion() as cur:
            # El bloqueo del usuario serializa aperturas simultáneas de su caja.
            self._operador(cur, id_recepcionista)
            cur.execute("SELECT id_turno FROM turnos_caja WHERE id_recepcionista=%s AND estado_caja='abierto' FOR UPDATE", (id_recepcionista,))
            if cur.fetchall():
                raise TurnoCajaError("Ya tenés un turno abierto. Cerralo antes de abrir otro.")
            cur.execute("INSERT INTO turnos_caja (id_recepcionista, saldo_inicial, estado_caja) VALUES (%s,%s,'abierto')", (id_recepcionista, saldo_inicial))
            return TurnoCaja(cur.lastrowid, id_recepcionista, saldo_inicial=saldo_inicial)

    def cerrar_turno(self, id_turno: int, id_usuario: int) -> dict:
        id_turno = V.entero(id_turno, "id_turno")
        id_usuario = V.entero(id_usuario, "id_usuario")
        with self._transaccion() as cur:
            self._operador(cur, id_usuario)
            cur.execute("SELECT * FROM turnos_caja WHERE id_turno=%s FOR UPDATE", (id_turno,))
            fila = cur.fetchone()
            if not fila or fila["id_recepcionista"] != id_usuario:
                raise TurnoCajaError("Solo podés cerrar tu propio turno de caja.")
            if fila["estado_caja"] != "abierto":
                raise TurnoCajaError("El turno ya está cerrado.")
            cur.execute("""SELECT
                COALESCE(SUM(CASE WHEN tipo_pago='efectivo' THEN monto ELSE 0 END),0) AS efectivo,
                COALESCE(SUM(CASE WHEN tipo_pago='digital' THEN monto ELSE 0 END),0) AS digital,
                COUNT(*) AS cantidad FROM pagos WHERE id_turno=%s""", (id_turno,))
            totales = cur.fetchone()
            efectivo = V.decimal(totales["efectivo"], "ingresos_efectivo")
            digital = V.decimal(totales["digital"], "ingresos_digitales")
            cur.execute("""UPDATE turnos_caja SET estado_caja='cerrado', fecha_cierre=NOW(),
                ingresos_efectivo=%s, ingresos_digitales=%s WHERE id_turno=%s""", (efectivo, digital, id_turno))
            cur.execute("SELECT fecha_cierre FROM turnos_caja WHERE id_turno=%s", (id_turno,))
            fecha = cur.fetchone()["fecha_cierre"]
            return {"id_turno": id_turno, "fecha_cierre": fecha.isoformat(),
                    "saldo_inicial": float(fila["saldo_inicial"]), "ingresos_efectivo": efectivo,
                    "ingresos_digitales": digital, "total_caja_fisica": round(float(fila["saldo_inicial"]) + efectivo, 2),
                    "total_ingresos": round(efectivo + digital, 2), "cantidad_operaciones": totales["cantidad"]}

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
