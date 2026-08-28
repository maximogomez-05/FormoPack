"""Controlador de Envíos y Cotización — RF 2.2 / RF 2.3 / RF 2.4 / RF 2.5."""

import logging
from typing import Optional
from datetime import datetime

from app.core.database import DatabaseManager
from app.models.envio import Envio
from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from app.models.pago import Pago, PagoEfectivo, PagoDigital
from app.models.historial_estado import HistorialEstado
from app.services.cotizador import Cotizador
from app.services.generador_guia import GeneradorGuia
from config.settings import EstadosEnvio
from app.utils.exceptions import (
    DatabaseQueryError,
    EnvioNotFoundError,
    ValidationError,
    CotizacionError,
)

logger = logging.getLogger(__name__)


class EnvioController:
    """Controlador principal de envíos, cotización y pagos.

    Cubre:
    - RF 2.2: Cotizador por Aforo
    - RF 2.3: Regla de Descuento Multibulto
    - RF 2.4: Seguros y Valor Declarado
    - RF 2.5: Integración de Pagos (Efectivo/Digital)
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self._db = db_manager or DatabaseManager.get_instance()
        self._cotizador = Cotizador()
        self._generador = GeneradorGuia()

    def cotizar_envio(
        self,
        bultos_data: list[dict],
        id_localidad_destino: int,
        valor_declarado: float = 0.0,
        id_seguro: Optional[int] = None,
    ) -> dict:
        """Cotiza un envío sin registrarlo (solo cálculo de tarifa).

        Args:
            bultos_data: Lista de dicts con {peso_real, peso_volumetrico, es_fragil}.
            id_localidad_destino: ID de la localidad de destino.
            valor_declarado: Valor declarado del contenido.
            id_seguro: ID del seguro a aplicar (opcional).

        Returns:
            Diccionario con el desglose de la cotización.
        """
        localidad = self._obtener_localidad(id_localidad_destino)
        seguro = self._obtener_seguro(id_seguro) if id_seguro else None

        bultos = [
            Bulto(
                id_bulto=0,
                id_envio=0,
                peso_real=float(b["peso_real"]),
                peso_volumetrico=float(b["peso_volumetrico"]),
                es_fragil=bool(b.get("es_fragil", False)),
            )
            for b in bultos_data
        ]

        return self._cotizador.calcular_tarifa(bultos, localidad, valor_declarado, seguro)

    def crear_envio(
        self,
        id_remitente: int,
        id_destinatario: int,
        id_localidad_destino: int,
        direccion_destino: str,
        bultos_data: list[dict],
        modalidad_pago: str = "efectivo",
        valor_declarado: float = 0.0,
        id_seguro: Optional[int] = None,
    ) -> dict:
        """Crea un envío completo: genera guía, registra bultos, cotiza y persiste.

        Args:
            id_remitente: ID del cliente remitente.
            id_destinatario: ID del cliente destinatario.
            id_localidad_destino: ID de la localidad de destino.
            direccion_destino: Dirección de entrega.
            bultos_data: Lista de dicts con datos de cada bulto.
            modalidad_pago: 'efectivo', 'digital' o 'cuenta_corriente'.
            valor_declarado: Valor declarado del contenido.
            id_seguro: ID del seguro (opcional).

        Returns:
            Diccionario con datos del envío creado y cotización.
        """
        if not direccion_destino or not direccion_destino.strip():
            raise ValidationError(field="direccion_destino", reason="La direccion es obligatoria.")
        if not bultos_data:
            raise ValidationError(field="bultos", reason="El envio debe tener al menos un bulto.")

        # Cotizar
        cotizacion = self.cotizar_envio(bultos_data, id_localidad_destino, valor_declarado, id_seguro)

        # Generar número de guía
        correlativo_actual = self._obtener_correlativo_diario()
        nro_guia = self._generador.generar_nro_guia(correlativo_actual)

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()

            # Insertar envío
            sql_envio = """
                INSERT INTO envios
                    (nro_guia, id_remitente, id_destinatario, id_localidad_destino,
                     id_seguro, direccion_destino, valor_declarado, modalidad_pago,
                     costo_total, estado_actual, es_devolucion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql_envio, (
                nro_guia, id_remitente, id_destinatario, id_localidad_destino,
                id_seguro, direccion_destino.strip(), valor_declarado, modalidad_pago,
                cotizacion["costo_total"], EstadosEnvio.RECIBIDO, False,
            ))
            id_envio = cursor.lastrowid

            # Insertar bultos
            sql_bulto = """
                INSERT INTO bultos (id_envio, peso_real, peso_volumetrico, es_fragil)
                VALUES (%s, %s, %s, %s)
            """
            for b in bultos_data:
                cursor.execute(sql_bulto, (
                    id_envio,
                    float(b["peso_real"]),
                    float(b["peso_volumetrico"]),
                    bool(b.get("es_fragil", False)),
                ))

            # Registrar estado inicial en historial
            sql_historial = """
                INSERT INTO historial_estados (id_envio, estado, ubicacion, observacion)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql_historial, (
                id_envio, EstadosEnvio.RECIBIDO, "Sucursal Origen", "Envio recibido en mostrador.",
            ))

            conn.commit()
            cursor.close()

            logger.info("Envio creado: guia=%s, costo=$%.2f", nro_guia, cotizacion["costo_total"])

            return {
                "id_envio": id_envio,
                "nro_guia": nro_guia,
                "cotizacion": cotizacion,
                "estado": EstadosEnvio.RECIBIDO,
            }

        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseQueryError(f"Error al crear envio: {e}") from e
        finally:
            if conn:
                conn.close()

    def registrar_pago(
        self,
        id_envio: int,
        monto: float,
        tipo_pago: str = "efectivo",
        id_turno: Optional[int] = None,
        monto_entregado: float = 0.0,
        id_transaccion_qr: Optional[str] = None,
        billetera_virtual: Optional[str] = None,
    ) -> dict:
        """Registra un pago contra un envío.

        Args:
            id_envio: ID del envío.
            monto: Monto a cobrar.
            tipo_pago: 'efectivo' o 'digital'.
            id_turno: ID del turno de caja activo.
            monto_entregado: Monto entregado por el cliente (solo efectivo).
            id_transaccion_qr: ID de transacción QR (solo digital).
            billetera_virtual: Nombre de billetera (solo digital).

        Returns:
            Diccionario con datos del pago registrado.
        """
        sql = """
            INSERT INTO pagos
                (id_envio, id_turno, monto, tipo_pago, monto_entregado,
                 id_transaccion_qr, billetera_virtual)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (
                id_envio, id_turno, monto, tipo_pago, monto_entregado,
                id_transaccion_qr, billetera_virtual,
            ))
            conn.commit()
            id_pago = cursor.lastrowid
            cursor.close()

            vuelto = round(max(0, monto_entregado - monto), 2) if tipo_pago == "efectivo" else 0.0

            logger.info("Pago #%d registrado: $%.2f (%s) para envio #%d", id_pago, monto, tipo_pago, id_envio)

            return {
                "id_pago": id_pago,
                "id_envio": id_envio,
                "monto": monto,
                "tipo_pago": tipo_pago,
                "vuelto": vuelto,
            }

        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseQueryError(f"Error al registrar pago: {e}") from e
        finally:
            if conn:
                conn.close()

    def obtener_por_guia(self, nro_guia: str) -> Envio:
        """Obtiene un envío por su número de guía.

        Args:
            nro_guia: Número de guía del envío.

        Returns:
            Instancia de Envio.

        Raises:
            EnvioNotFoundError: Si no se encuentra el envío.
        """
        sql = "SELECT * FROM envios WHERE nro_guia = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (nro_guia.strip(),))
            fila = cursor.fetchone()
            cursor.close()

            if not fila:
                raise EnvioNotFoundError(nro_guia=nro_guia)

            return Envio.from_db_row(fila)

        except EnvioNotFoundError:
            raise
        except Exception as e:
            raise DatabaseQueryError(f"Error al buscar envio: {e}") from e
        finally:
            if conn:
                conn.close()

    # --- Métodos internos ---

    def _obtener_localidad(self, id_localidad: int) -> Localidad:
        """Obtiene una localidad por ID desde la BD."""
        sql = "SELECT * FROM localidades WHERE id_localidad = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (id_localidad,))
            fila = cursor.fetchone()
            cursor.close()
            if not fila:
                raise CotizacionError(f"Localidad no encontrada con ID: {id_localidad}")
            return Localidad.from_db_row(fila)
        except CotizacionError:
            raise
        except Exception as e:
            raise DatabaseQueryError(f"Error al obtener localidad: {e}") from e
        finally:
            if conn:
                conn.close()

    def _obtener_seguro(self, id_seguro: int) -> Seguro:
        """Obtiene un seguro por ID desde la BD."""
        sql = "SELECT * FROM seguros WHERE id_seguro = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (id_seguro,))
            fila = cursor.fetchone()
            cursor.close()
            if not fila:
                raise CotizacionError(f"Seguro no encontrado con ID: {id_seguro}")
            return Seguro.from_db_row(fila)
        except CotizacionError:
            raise
        except Exception as e:
            raise DatabaseQueryError(f"Error al obtener seguro: {e}") from e
        finally:
            if conn:
                conn.close()

    def _obtener_correlativo_diario(self) -> int:
        """Obtiene el último correlativo de guía del día actual."""
        fecha_hoy = datetime.now().strftime("%Y%m%d")
        patron = f"FPX-{fecha_hoy}-%"
        sql = "SELECT COUNT(*) as total FROM envios WHERE nro_guia LIKE %s"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (patron,))
            fila = cursor.fetchone()
            cursor.close()
            return fila["total"] if fila else 0
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
