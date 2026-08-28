"""Modelo de Envío (Entidad central del sistema) — RF 2."""

from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from config.settings import EstadosEnvio

if TYPE_CHECKING:
    from app.models.bulto import Bulto

logger = logging.getLogger(__name__)


class Envio:
    """Entidad central que representa un envío/encomienda en el sistema.

    Mapea a la tabla `envios` del DER.
    Un envío contiene 1 o más bultos, tiene un remitente y un destinatario,
    y atraviesa un ciclo de vida de estados (recibido → en_planta → en_ruta → entregado).
    """

    def __init__(
        self,
        id_envio: int,
        nro_guia: str,
        id_remitente: int,
        id_destinatario: int,
        id_localidad_destino: int,
        direccion_destino: str,
        valor_declarado: float = 0.0,
        modalidad_pago: str = "efectivo",
        costo_total: float = 0.0,
        estado_actual: str = EstadosEnvio.RECIBIDO,
        es_devolucion: bool = False,
        id_seguro: Optional[int] = None,
        id_hoja_ruta: Optional[int] = None,
        fecha_creacion: Optional[datetime] = None,
    ) -> None:
        self._id_envio = id_envio
        self._nro_guia = nro_guia
        self._id_remitente = id_remitente
        self._id_destinatario = id_destinatario
        self._id_localidad_destino = id_localidad_destino
        self._direccion_destino = direccion_destino
        self._valor_declarado = valor_declarado
        self._modalidad_pago = modalidad_pago
        self._costo_total = costo_total
        self._estado_actual = estado_actual
        self._es_devolucion = es_devolucion
        self._id_seguro = id_seguro
        self._id_hoja_ruta = id_hoja_ruta
        self._fecha_creacion = fecha_creacion or datetime.now()
        self._bultos: list[Bulto] = []

    # --- Properties ---

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def nro_guia(self) -> str:
        return self._nro_guia

    @property
    def id_remitente(self) -> int:
        return self._id_remitente

    @property
    def id_destinatario(self) -> int:
        return self._id_destinatario

    @property
    def id_localidad_destino(self) -> int:
        return self._id_localidad_destino

    @property
    def direccion_destino(self) -> str:
        return self._direccion_destino

    @property
    def valor_declarado(self) -> float:
        return self._valor_declarado

    @property
    def modalidad_pago(self) -> str:
        return self._modalidad_pago

    @property
    def costo_total(self) -> float:
        return self._costo_total

    @costo_total.setter
    def costo_total(self, value: float) -> None:
        self._costo_total = round(value, 2)

    @property
    def estado_actual(self) -> str:
        return self._estado_actual

    @property
    def es_devolucion(self) -> bool:
        return self._es_devolucion

    @property
    def id_seguro(self) -> Optional[int]:
        return self._id_seguro

    @property
    def id_hoja_ruta(self) -> Optional[int]:
        return self._id_hoja_ruta

    @property
    def fecha_creacion(self) -> datetime:
        return self._fecha_creacion

    @property
    def bultos(self) -> list:
        return self._bultos.copy()

    @property
    def cantidad_bultos(self) -> int:
        return len(self._bultos)

    # --- Métodos de negocio (UML) ---

    def agregar_bulto(self, bulto: "Bulto") -> None:
        """Agrega un bulto al envío.

        Args:
            bulto: Instancia de Bulto a agregar.
        """
        self._bultos.append(bulto)

    def registrar_estado(self, nuevo_estado: str, motivo: Optional[str] = None) -> None:
        """Actualiza el estado actual del envío.

        Args:
            nuevo_estado: Nuevo estado del ciclo de vida.
            motivo: Observación opcional del cambio.
        """
        if nuevo_estado not in EstadosEnvio.TODOS:
            raise ValueError(f"Estado no valido: '{nuevo_estado}'")
        self._estado_actual = nuevo_estado
        logger.info(
            "Envio %s cambio a estado '%s'. Motivo: %s",
            self._nro_guia, nuevo_estado, motivo or "N/A",
        )

    def calcular_costo_total(self, tarifa_por_bulto: list[float], costo_seguro: float = 0.0) -> float:
        """Calcula y establece el costo total del envío.

        Args:
            tarifa_por_bulto: Lista de tarifas individuales por cada bulto.
            costo_seguro: Costo adicional del seguro.

        Returns:
            Costo total calculado.
        """
        subtotal = sum(tarifa_por_bulto)
        self._costo_total = round(subtotal + costo_seguro, 2)
        return self._costo_total

    # --- Serialización ---

    def to_dict(self) -> dict:
        """Serializa a diccionario."""
        return {
            "id_envio": self._id_envio,
            "nro_guia": self._nro_guia,
            "id_remitente": self._id_remitente,
            "id_destinatario": self._id_destinatario,
            "id_localidad_destino": self._id_localidad_destino,
            "direccion_destino": self._direccion_destino,
            "valor_declarado": self._valor_declarado,
            "modalidad_pago": self._modalidad_pago,
            "costo_total": self._costo_total,
            "estado_actual": self._estado_actual,
            "es_devolucion": self._es_devolucion,
            "id_seguro": self._id_seguro,
            "id_hoja_ruta": self._id_hoja_ruta,
            "fecha_creacion": self._fecha_creacion.isoformat() if self._fecha_creacion else None,
            "cantidad_bultos": self.cantidad_bultos,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Envio":
        """Instancia un Envio desde una fila de base de datos."""
        return cls(
            id_envio=row["id_envio"],
            nro_guia=row["nro_guia"],
            id_remitente=row["id_remitente"],
            id_destinatario=row["id_destinatario"],
            id_localidad_destino=row["id_localidad_destino"],
            direccion_destino=row["direccion_destino"],
            valor_declarado=float(row.get("valor_declarado", 0)),
            modalidad_pago=row.get("modalidad_pago", "efectivo"),
            costo_total=float(row.get("costo_total", 0)),
            estado_actual=row.get("estado_actual", EstadosEnvio.RECIBIDO),
            es_devolucion=bool(row.get("es_devolucion", False)),
            id_seguro=row.get("id_seguro"),
            id_hoja_ruta=row.get("id_hoja_ruta"),
            fecha_creacion=row.get("fecha_creacion"),
        )

    def __repr__(self) -> str:
        return (
            f"<Envio id={self._id_envio} guia='{self._nro_guia}' "
            f"estado='{self._estado_actual}' bultos={self.cantidad_bultos}>"
        )
