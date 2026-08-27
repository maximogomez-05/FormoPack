"""Conexión a MySQL con patrón Singleton y Connection Pool."""

import logging
from typing import Optional
from mysql.connector import pooling, Error as MySQLError
from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool

from config.settings import DatabaseConfig
from app.utils.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Administrador de conexiones MySQL (Singleton)."""

    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[MySQLConnectionPool] = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    def _initialize_pool(self) -> None:
        """Inicializa el pool de conexiones MySQL."""
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="formopack_pool",
                pool_size=DatabaseConfig.POOL_SIZE,
                pool_reset_session=True,
                host=DatabaseConfig.HOST,
                port=DatabaseConfig.PORT,
                database=DatabaseConfig.NAME,
                user=DatabaseConfig.USER,
                password=DatabaseConfig.PASSWORD,
                charset=DatabaseConfig.CHARSET,
                use_unicode=True,
                connect_timeout=DatabaseConfig.CONNECT_TIMEOUT,
            )
            logger.info("Pool MySQL inicializado.")
        except MySQLError as e:
            logger.critical("Error al inicializar pool MySQL: %s", e)
            raise DatabaseConnectionError(
                f"No se pudo conectar a MySQL en {DatabaseConfig.HOST}:{DatabaseConfig.PORT}. {e}"
            ) from e

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        """Obtiene la instancia única."""
        return cls()

    def get_connection(self) -> MySQLConnection:
        """Obtiene una conexión activa del pool."""
        try:
            return self._pool.get_connection()
        except MySQLError as e:
            logger.error("Error al obtener conexión del pool: %s", e)
            raise DatabaseConnectionError(f"Pool agotado o servidor no disponible: {e}") from e

    def test_connection(self) -> bool:
        """Prueba la conexión al servidor."""
        try:
            conn = self.get_connection()
            conn.ping(reconnect=True, attempts=3, delay=1)
            conn.close()
            return True
        except DatabaseConnectionError:
            raise
        except MySQLError as e:
            raise DatabaseConnectionError(f"Ping a MySQL falló: {e}") from e
