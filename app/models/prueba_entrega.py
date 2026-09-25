"""Modelos de Prueba de Entrega y Entrega Fallida (RF 4.2 / RF 4.5).

Mapean a la tabla `intentos_entrega` del DER.
PruebaDeEntrega representa el registro de un intento de entrega (exitosa o no).
EntregaFallida es una subclase especializada que agrega el manejo de devoluciones.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class PruebaDeEntrega:
    """Evidencia del intento de entrega de un envío (exitoso o fallido).

    Mapea a la tabla `intentos_entrega` del DER.
    Contiene los datos capturados por el chofer en el campo:
    DNI del receptor, firma digital, foto del remito y coordenadas GPS.
    """

    TIPOS_VALIDOS = {"entregado", "fallido"}

    def __init__(
        self,
        id_intento: Optional[int],
        id_envio: int,
        id_hoja_ruta: int,
        tipo_intento: str,
        dni_receptor: Optional[str] = None,
        firma_receptor: Optional[str] = None,
        foto_remito: Optional[str] = None,
        coordenadas_gps: Optional[str] = None,
        motivo_fallo: Optional[str] = None,
        fecha_hora: Optional[datetime] = None,
    ) -> None:
        self._id_intento = id_intento
        self._id_envio = id_envio
        self._id_hoja_ruta = id_hoja_ruta
        self._tipo_intento = tipo_intento
        self._dni_receptor = dni_receptor
        self._firma_receptor = firma_receptor
        self._foto_remito = foto_remito
        self._coordenadas_gps = coordenadas_gps
        self._motivo_fallo = motivo_fallo
        self._fecha_hora = fecha_hora or datetime.now()

    # --- Properties ---

    @property
    def id_intento(self) -> Optional[int]:
        return self._id_intento

    @property
    def id_envio(self) -> int:
        return self._id_envio

    @property
    def id_hoja_ruta(self) -> int:
        return self._id_hoja_ruta

    @property
    def tipo_intento(self) -> str:
        return self._tipo_intento

    @property
    def dni_receptor(self) -> Optional[str]:
        return self._dni_receptor

    @property
    def firma_receptor(self) -> Optional[str]:
        return self._firma_receptor

    @property
    def foto_remito(self) -> Optional[str]:
        return self._foto_remito

    @property
    def coordenadas_gps(self) -> Optional[str]:
        return self._coordenadas_gps

    @property
    def motivo_fallo(self) -> Optional[str]:
        return self._motivo_fallo

    @property
    def fecha_hora(self) -> datetime:
        return self._fecha_hora

    # --- Métodos de negocio (UML) ---

    def validar_entrega(self) -> bool:
        """Valida que la prueba de entrega sea coherente con su tipo.

        Para una entrega exitosa, exige DNI y firma del receptor.
        Para una entrega fallida, exige un motivo de fallo.

        Returns:
            True si la evidencia es válida para el tipo de intento.

        Raises:
            ValidationError: Si falta algún dato obligatorio.
        """
        if self._tipo_intento not in self.TIPOS_VALIDOS:
            raise ValidationError(
                field="tipo_intento",
                reason=f"Tipo de intento no válido: '{self._tipo_intento}'. Debe ser 'entregado' o 'fallido'.",
            )

        if self._tipo_intento == "entregado":
            if not self._dni_receptor or not self._dni_receptor.strip():
                raise ValidationError(
                    field="dni_receptor",
                    reason="Una entrega exitosa requiere el DNI del receptor.",
                )
            if not self._firma_receptor:
                raise ValidationError(
                    field="firma_receptor",
                    reason="Una entrega exitosa requiere la firma del receptor.",
                )

        return True

    def to_dict(self) -> dict:
        """Serializa a diccionario (compatible con la tabla intentos_entrega)."""
        return {
            "id_intento": self._id_intento,
            "id_envio": self._id_envio,
            "id_hoja_ruta": self._id_hoja_ruta,
            "tipo_intento": self._tipo_intento,
            "dni_receptor": self._dni_receptor,
            "firma_receptor": self._firma_receptor,
            "foto_remito": self._foto_remito,
            "coordenadas_gps": self._coordenadas_gps,
            "motivo_fallo": self._motivo_fallo,
            "fecha_hora": self._fecha_hora.isoformat() if self._fecha_hora else None,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "PruebaDeEntrega":
        """Instancia la subclase correcta según tipo_intento."""
        tipo = row.get("tipo_intento", "entregado")
        kwargs = dict(
            id_intento=row.get("id_intento"),
            id_envio=row["id_envio"],
            id_hoja_ruta=row["id_hoja_ruta"],
            tipo_intento=tipo,
            dni_receptor=row.get("dni_receptor"),
            firma_receptor=row.get("firma_receptor"),
            foto_remito=row.get("foto_remito"),
            coordenadas_gps=row.get("coordenadas_gps"),
            motivo_fallo=row.get("motivo_fallo"),
            fecha_hora=row.get("fecha_hora"),
        )
        if tipo == "fallido":
            return EntregaFallida(**kwargs)
        return cls(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<PruebaDeEntrega envio={self._id_envio} "
            f"tipo='{self._tipo_intento}' hoja={self._id_hoja_ruta}>"
        )


class EntregaFallida(PruebaDeEntrega):
    """Prueba de entrega que no pudo completarse exitosamente.

    Subclase de PruebaDeEntrega especializada para el flujo de fallos:
    captura el motivo y provee la acción de devolución a origen (RF 4.5).
    """

    def __init__(self, motivo_fallo: str, **kwargs) -> None:
        # Fuerza tipo_intento='fallido' independientemente de lo que venga en kwargs
        kwargs["tipo_intento"] = "fallido"
        super().__init__(**kwargs)
        # Sobreescribir con el valor tipado (por si vino vacío en kwargs)
        self._motivo_fallo = motivo_fallo

    def procesar_retorno_devolucion(self) -> str:
        """Genera la observación para el historial de estados al devolver a origen.

        Returns:
            Texto de observación para registrar en historial_estados.

        Raises:
            ValidationError: Si no hay motivo de fallo registrado.
        """
        if not self._motivo_fallo or not self._motivo_fallo.strip():
            raise ValidationError(
                field="motivo_fallo",
                reason="No se puede procesar la devolución sin un motivo registrado.",
            )
        observacion = f"Devolución a origen. Motivo del fallo previo: {self._motivo_fallo.strip()}"
        logger.info(
            "Devolución procesada para envio %d. Motivo: %s",
            self._id_envio,
            self._motivo_fallo,
        )
        return observacion

    def validar_entrega(self) -> bool:
        """Valida que la entrega fallida tenga motivo."""
        if not self._motivo_fallo or not self._motivo_fallo.strip():
            raise ValidationError(
                field="motivo_fallo",
                reason="Una entrega fallida requiere un motivo.",
            )
        return True

    def __repr__(self) -> str:
        return (
            f"<EntregaFallida envio={self._id_envio} "
            f"motivo='{self._motivo_fallo}' hoja={self._id_hoja_ruta}>"
        )
