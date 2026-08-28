"""Modelo de Turno de Caja — RF 2.6."""

from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from app.utils.exceptions import TurnoCajaError

if TYPE_CHECKING:
    from app.models.pago import Pago

logger = logging.getLogger(__name__)


class TurnoCaja:
    """Entidad que representa un turno de caja de una recepcionista.

    Mapea a la tabla `turnos_caja` del DER.
    Gestiona la apertura/cierre de caja discriminando ingresos
    en efectivo de ingresos digitales (RF 2.6 — Conciliación de Caja).
    """

    def __init__(
        self,
        id_turno: int,
        id_recepcionista: int,
        fecha_apertura: Optional[datetime] = None,
        fecha_cierre: Optional[datetime] = None,
        saldo_inicial: float = 0.0,
        ingresos_efectivo: float = 0.0,
        ingresos_digitales: float = 0.0,
        estado_caja: str = "abierto",
    ) -> None:
        self._id_turno = id_turno
        self._id_recepcionista = id_recepcionista
        self._fecha_apertura = fecha_apertura or datetime.now()
        self._fecha_cierre = fecha_cierre
        self._saldo_inicial = saldo_inicial
        self._ingresos_efectivo = ingresos_efectivo
        self._ingresos_digitales = ingresos_digitales
        self._estado_caja = estado_caja

    # --- Properties ---

    @property
    def id_turno(self) -> int:
        return self._id_turno

    @property
    def id_recepcionista(self) -> int:
        return self._id_recepcionista

    @property
    def fecha_apertura(self) -> datetime:
        return self._fecha_apertura

    @property
    def fecha_cierre(self) -> Optional[datetime]:
        return self._fecha_cierre

    @property
    def saldo_inicial(self) -> float:
        return self._saldo_inicial

    @property
    def ingresos_efectivo(self) -> float:
        return self._ingresos_efectivo

    @property
    def ingresos_digitales(self) -> float:
        return self._ingresos_digitales

    @property
    def estado_caja(self) -> str:
        return self._estado_caja

    @property
    def total_caja(self) -> float:
        """Total en caja física (saldo inicial + efectivo)."""
        return round(self._saldo_inicial + self._ingresos_efectivo, 2)

    @property
    def total_ingresos(self) -> float:
        """Total de ingresos del turno (efectivo + digital)."""
        return round(self._ingresos_efectivo + self._ingresos_digitales, 2)

    # --- Métodos de negocio (UML) ---

    def registrar_ingreso(self, pago: "Pago") -> None:
        """Registra un ingreso en el turno de caja, discriminando por tipo.

        Args:
            pago: Instancia de Pago a registrar.

        Raises:
            TurnoCajaError: Si la caja no está abierta.
        """
        if self._estado_caja != "abierto":
            raise TurnoCajaError("No se puede registrar un ingreso en una caja cerrada.")

        if pago.tipo_pago == "efectivo":
            self._ingresos_efectivo = round(self._ingresos_efectivo + pago.monto, 2)
        elif pago.tipo_pago == "digital":
            self._ingresos_digitales = round(self._ingresos_digitales + pago.monto, 2)

        logger.info(
            "Turno #%d: Ingreso $%.2f (%s). Efectivo acum: $%.2f | Digital acum: $%.2f",
            self._id_turno, pago.monto, pago.tipo_pago,
            self._ingresos_efectivo, self._ingresos_digitales,
        )

    def realizar_cierre_caja(self) -> dict:
        """Cierra el turno de caja y genera el resumen de conciliación.

        Returns:
            Diccionario con el resumen del cierre.

        Raises:
            TurnoCajaError: Si la caja ya está cerrada.
        """
        if self._estado_caja == "cerrado":
            raise TurnoCajaError("La caja ya se encuentra cerrada.")

        self._estado_caja = "cerrado"
        self._fecha_cierre = datetime.now()

        resumen = {
            "id_turno": self._id_turno,
            "fecha_apertura": self._fecha_apertura.isoformat(),
            "fecha_cierre": self._fecha_cierre.isoformat(),
            "saldo_inicial": self._saldo_inicial,
            "ingresos_efectivo": self._ingresos_efectivo,
            "ingresos_digitales": self._ingresos_digitales,
            "total_caja_fisica": self.total_caja,
            "total_ingresos": self.total_ingresos,
        }

        logger.info("Turno #%d cerrado. Resumen: %s", self._id_turno, resumen)
        return resumen

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_turno": self._id_turno,
            "id_recepcionista": self._id_recepcionista,
            "fecha_apertura": self._fecha_apertura.isoformat() if self._fecha_apertura else None,
            "fecha_cierre": self._fecha_cierre.isoformat() if self._fecha_cierre else None,
            "saldo_inicial": self._saldo_inicial,
            "ingresos_efectivo": self._ingresos_efectivo,
            "ingresos_digitales": self._ingresos_digitales,
            "estado_caja": self._estado_caja,
            "total_caja_fisica": self.total_caja,
            "total_ingresos": self.total_ingresos,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "TurnoCaja":
        """Instancia un TurnoCaja desde una fila de base de datos."""
        return cls(
            id_turno=row["id_turno"],
            id_recepcionista=row["id_recepcionista"],
            fecha_apertura=row.get("fecha_apertura"),
            fecha_cierre=row.get("fecha_cierre"),
            saldo_inicial=float(row.get("saldo_inicial", 0)),
            ingresos_efectivo=float(row.get("ingresos_efectivo", 0)),
            ingresos_digitales=float(row.get("ingresos_digitales", 0)),
            estado_caja=row.get("estado_caja", "abierto"),
        )

    def __repr__(self) -> str:
        return (
            f"<TurnoCaja id={self._id_turno} estado='{self._estado_caja}' "
            f"efectivo=${self._ingresos_efectivo} digital=${self._ingresos_digitales}>"
        )
