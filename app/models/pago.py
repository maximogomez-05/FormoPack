"""Modelo de Pago con herencia (Efectivo / Digital) — RF 2.5."""

from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class Pago:
    """Entidad base de un pago registrado contra un envío.

    Mapea a la tabla `pagos` del DER.
    Tiene dos especializaciones: PagoEfectivo y PagoDigital (UML).
    """

    def __init__(
        self,
        id_pago: int,
        id_envio: int,
        monto: float,
        fecha: Optional[datetime] = None,
        tipo_pago: str = "efectivo",
        id_turno: Optional[int] = None,
    ) -> None:
        self._id_pago = id_pago
        self._id_envio = id_envio
        self._monto = monto
        self._fecha = fecha or datetime.now()
        self._tipo_pago = tipo_pago
        self._id_turno = id_turno

    # --- Properties ---

    @property
    def id_pago(self) -> int:
        return self._id_pago

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def monto(self) -> float:
        return self._monto

    @property
    def fecha(self) -> datetime:
        return self._fecha

    @property
    def tipo_pago(self) -> str:
        return self._tipo_pago

    @property
    def id_turno(self) -> Optional[int]:
        return self._id_turno

    # --- Métodos de negocio (UML) ---

    def procesar_pago(self) -> bool:
        """Procesa el pago y lo marca como registrado.

        Returns:
            True si el pago fue procesado exitosamente.
        """
        if self._monto <= 0:
            return False
        logger.info("Pago #%d procesado: $%.2f (%s)", self._id_pago, self._monto, self._tipo_pago)
        return True

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_pago": self._id_pago,
            "id_envio": self._id_envio,
            "monto": self._monto,
            "fecha": self._fecha.isoformat() if self._fecha else None,
            "tipo_pago": self._tipo_pago,
            "id_turno": self._id_turno,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Pago":
        """Instancia la subclase correcta según tipo_pago."""
        tipo = row.get("tipo_pago", "efectivo")
        if tipo == "digital":
            return PagoDigital.from_db_row(row)
        return PagoEfectivo.from_db_row(row)

    def __repr__(self) -> str:
        return f"<Pago id={self._id_pago} monto=${self._monto} tipo='{self._tipo_pago}'>"


class PagoEfectivo(Pago):
    """Pago realizado en efectivo con control de vuelto."""

    def __init__(self, monto_entregado: float = 0.0, **kwargs) -> None:
        super().__init__(**kwargs, tipo_pago="efectivo")
        self._monto_entregado = monto_entregado

    @property
    def monto_entregado(self) -> float:
        return self._monto_entregado

    @property
    def vuelto(self) -> float:
        """Calcula el vuelto a devolver al cliente."""
        return round(max(0, self._monto_entregado - self._monto), 2)

    def to_dict(self) -> dict:
        """Serializa incluyendo monto entregado y vuelto."""
        data = super().to_dict()
        data["monto_entregado"] = self._monto_entregado
        data["vuelto"] = self.vuelto
        return data

    @classmethod
    def from_db_row(cls, row: dict) -> "PagoEfectivo":
        """Instancia un PagoEfectivo desde fila de BD."""
        return cls(
            id_pago=row["id_pago"],
            id_envio=row["id_envio"],
            monto=float(row["monto"]),
            fecha=row.get("fecha"),
            id_turno=row.get("id_turno"),
            monto_entregado=float(row.get("monto_entregado", 0)),
        )

    def __repr__(self) -> str:
        return f"<PagoEfectivo id={self._id_pago} monto=${self._monto} entregado=${self._monto_entregado}>"


class PagoDigital(Pago):
    """Pago realizado por billetera virtual / QR (MercadoPago)."""

    def __init__(
        self,
        id_transaccion_qr: Optional[str] = None,
        billetera_virtual: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs, tipo_pago="digital")
        self._id_transaccion_qr = id_transaccion_qr
        self._billetera_virtual = billetera_virtual

    @property
    def id_transaccion_qr(self) -> Optional[str]:
        return self._id_transaccion_qr

    @property
    def billetera_virtual(self) -> Optional[str]:
        return self._billetera_virtual

    def generar_qr(self, monto: float) -> str:
        """Genera un string representativo del QR para el monto dado.

        Nota: En producción se integraría con la API gratuita de MercadoPago.
        Por ahora genera un identificador interno.

        Returns:
            String con el código QR generado.
        """
        import uuid
        self._id_transaccion_qr = f"QR-{uuid.uuid4().hex[:12].upper()}"
        return self._id_transaccion_qr

    def to_dict(self) -> dict:
        """Serializa incluyendo datos de transacción digital."""
        data = super().to_dict()
        data["id_transaccion_qr"] = self._id_transaccion_qr
        data["billetera_virtual"] = self._billetera_virtual
        return data

    @classmethod
    def from_db_row(cls, row: dict) -> "PagoDigital":
        """Instancia un PagoDigital desde fila de BD."""
        return cls(
            id_pago=row["id_pago"],
            id_envio=row["id_envio"],
            monto=float(row["monto"]),
            fecha=row.get("fecha"),
            id_turno=row.get("id_turno"),
            id_transaccion_qr=row.get("id_transaccion_qr"),
            billetera_virtual=row.get("billetera_virtual"),
        )

    def __repr__(self) -> str:
        return (
            f"<PagoDigital id={self._id_pago} monto=${self._monto} "
            f"qr='{self._id_transaccion_qr}' billetera='{self._billetera_virtual}'>"
        )
