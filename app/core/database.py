"""Conexión a MySQL con patrón Singleton y Connection Pool."""

import logging
from contextlib import contextmanager
from typing import Generator, Any, Optional
from mysql.connector import pooling, Error as MySQLError
from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool

from config.settings import DatabaseConfig
from app.utils.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Administrador de conexiones MySQL (Singleton con soporte de Context Manager)."""

    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[MySQLConnectionPool] = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: Optional["DatabaseManager"]) -> None:
        """Permite inyectar un mock o instancia personalizada para pruebas unitarias."""
        cls._instance = instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reinicia la instancia única para aislar pruebas."""
        cls._instance = None
        cls._pool = None

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

    @contextmanager
    def connection(self) -> Generator[MySQLConnection, None, None]:
        """Context manager para conexiones MySQL seguras.

        Garantiza commit automático al finalizar el bloque con éxito,
        rollback automático en caso de error, y cierre/retorno de la conexión
        al pool en el bloque finally.
        """
        conn = self.get_connection()
        try:
            yield conn
            try:
                conn.commit()
            except Exception:
                pass
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def cursor(self, dictionary: bool = True) -> Generator[Any, None, None]:
        """Context manager para obtener un cursor con gestión automática de conexión."""
        with self.connection() as conn:
            cur = conn.cursor(dictionary=dictionary)
            try:
                yield cur
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

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
