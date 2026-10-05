"""Controlador CRUD de Clientes — RF 2.1."""

import logging
from typing import Optional

from app.core.database import DatabaseManager
from app.models.cliente import Cliente
from app.utils.exceptions import (
    ClienteNotFoundError,
    DatabaseQueryError,
    DuplicateError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class ClienteController:
    """Controlador para el registro y consulta de clientes (remitentes/destinatarios).

    Cubre RF 2.1: Registro de Clientes exigiendo DNI y Teléfono obligatorios.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self._db = db_manager or DatabaseManager.get_instance()

    def _tiene_columna_email(self) -> bool:
        """Compatibilidad con esquemas antiguos sin columna email."""
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SHOW COLUMNS FROM clientes LIKE 'email'")
            return cursor.fetchone() is not None
        except Exception:
            return False
        finally:
            if conn:
                conn.close()

    def registrar_cliente(
        self,
        dni: str,
        nombre_completo: str,
        telefono: str,
        email: Optional[str] = None,
    ) -> Cliente:
        """Registra un nuevo cliente en el sistema.

        Args:
            dni: Documento Nacional de Identidad (obligatorio).
            nombre_completo: Nombre completo del cliente.
            telefono: Teléfono de contacto (obligatorio).
            email: Correo electrónico de contacto (opcional).

        Returns:
            Instancia de Cliente registrado.

        Raises:
            ValidationError: Si faltan datos obligatorios.
            DuplicateError: Si el DNI ya está registrado.
        """
        email_limpio = email.strip() if email else None
        Cliente.validar_datos(dni, nombre_completo, telefono, email_limpio)

        # Verificar duplicado
        existente = self.buscar_por_dni(dni)
        if existente:
            raise DuplicateError(entity="Cliente", identifier=dni)

        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor()

            if self._tiene_columna_email():
                cursor.execute(
                    """
                        INSERT INTO clientes (dni, nombre_completo, telefono, email)
                        VALUES (%s, %s, %s, %s)
                    """,
                    (dni.strip(), nombre_completo.strip(), telefono.strip(), email_limpio),
                )
            else:
                cursor.execute(
                    """
                        INSERT INTO clientes (dni, nombre_completo, telefono)
                        VALUES (%s, %s, %s)
                    """,
                    (dni.strip(), nombre_completo.strip(), telefono.strip()),
                )

            conn.commit()
            id_nuevo = cursor.lastrowid
            cursor.close()

            cliente = Cliente(
                id_cliente=id_nuevo,
                dni=dni.strip(),
                nombre_completo=nombre_completo.strip(),
                telefono=telefono.strip(),
                email=email_limpio if self._tiene_columna_email() else None,
            )
            logger.info("Cliente registrado: %s", cliente)
            return cliente

        except DuplicateError:
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseQueryError(f"Error al registrar cliente: {e}") from e
        finally:
            if conn:
                conn.close()

    def buscar_por_dni(self, dni: str) -> Optional[Cliente]:
        """Busca un cliente por su DNI.

        Args:
            dni: Documento Nacional de Identidad.

        Returns:
            Instancia de Cliente o None si no se encuentra.
        """
        sql = "SELECT * FROM clientes WHERE dni = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (dni.strip(),))
            fila = cursor.fetchone()
            cursor.close()
            return Cliente.from_db_row(fila) if fila else None
        except Exception as e:
            raise DatabaseQueryError(f"Error al buscar cliente por DNI: {e}") from e
        finally:
            if conn:
                conn.close()

    def buscar_por_telefono(self, telefono: str) -> Optional[Cliente]:
        """Busca un cliente por su teléfono.

        Args:
            telefono: Número de teléfono de contacto.

        Returns:
            Instancia de Cliente o None si no se encuentra.
        """
        sql = "SELECT * FROM clientes WHERE telefono = %s LIMIT 1"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (telefono.strip(),))
            fila = cursor.fetchone()
            cursor.close()
            return Cliente.from_db_row(fila) if fila else None
        except Exception as e:
            raise DatabaseQueryError(f"Error al buscar cliente por telefono: {e}") from e
        finally:
            if conn:
                conn.close()

    def listar_clientes(self, limite: int = 50) -> list[Cliente]:
        """Lista los clientes registrados en el sistema.

        Args:
            limite: Cantidad máxima de resultados.

        Returns:
            Lista de instancias de Cliente.
        """
        sql = "SELECT * FROM clientes ORDER BY nombre_completo ASC LIMIT %s"
        conn = None
        try:
            conn = self._db.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (limite,))
            filas = cursor.fetchall()
            cursor.close()
            return [Cliente.from_db_row(f) for f in filas]
        except Exception as e:
            raise DatabaseQueryError(f"Error al listar clientes: {e}") from e
        finally:
            if conn:
                conn.close()

    def obtener_o_crear(self, dni: str, nombre_completo: str, telefono: str, email: Optional[str] = None) -> Cliente:
        """Obtiene un cliente existente por DNI, o lo crea si no existe.

        Args:
            dni: Documento Nacional de Identidad.
            nombre_completo: Nombre completo.
            telefono: Teléfono de contacto.
            email: Correo electrónico (opcional).

        Returns:
            Instancia de Cliente (existente o recién creado).
        """
        existente = self.buscar_por_dni(dni)
        if existente:
            return existente
        return self.registrar_cliente(dni, nombre_completo, telefono, email)
