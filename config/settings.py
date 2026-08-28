"""Configuración global del sistema."""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class DatabaseConfig:
    """Parámetros de conexión MySQL."""
    HOST: str = os.getenv("DB_HOST", "localhost")
    PORT: int = int(os.getenv("DB_PORT", 3306))
    NAME: str = os.getenv("DB_NAME", "formopack_db")
    USER: str = os.getenv("DB_USER", "root")
    PASSWORD: str = os.getenv("DB_PASSWORD", "")
    CHARSET: str = "utf8mb4"
    POOL_SIZE: int = 5
    CONNECT_TIMEOUT: int = 10


class AppConfig:
    """Ajustes de la aplicación."""
    APP_NAME: str = "Formopack Express"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("APP_DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "secret-key")
    BCRYPT_ROUNDS: int = 12


class RoleConfig:
    """Roles del sistema."""
    ADMINISTRADOR: str = "administrador"
    RECEPCIONISTA: str = "recepcionista"
    CHOFER: str = "chofer"
    TODOS: list[str] = [ADMINISTRADOR, RECEPCIONISTA, CHOFER]


class CotizadorConfig:
    """Parámetros del motor de cotización (RF 2.2 / RF 2.3)."""
    TARIFA_BASE_KG: float = float(os.getenv("TARIFA_BASE_KG", "150.0"))
    FACTOR_VOLUMETRICO: int = int(os.getenv("FACTOR_VOLUMETRICO", "5000"))
    DESCUENTO_MULTIBULTO: float = 0.50  # 50% de descuento al 2do bulto en adelante
    TARIFA_MINIMA: float = float(os.getenv("TARIFA_MINIMA", "500.0"))
    RECARGO_FRAGIL: float = float(os.getenv("RECARGO_FRAGIL", "0.10"))  # 10% adicional


class EstadosEnvio:
    """Estados posibles del ciclo de vida de un envío."""
    RECIBIDO: str = "recibido"
    EN_PLANTA: str = "en_planta"
    EN_RUTA: str = "en_ruta"
    ENTREGADO: str = "entregado"
    FALLIDO: str = "fallido"
    DEVOLUCION: str = "devolucion"
    SINIESTRO: str = "siniestro"
    TODOS: list[str] = [RECIBIDO, EN_PLANTA, EN_RUTA, ENTREGADO, FALLIDO, DEVOLUCION, SINIESTRO]


class ModalidadPago:
    """Modalidades de pago aceptadas."""
    EFECTIVO: str = "efectivo"
    DIGITAL: str = "digital"
    CUENTA_CORRIENTE: str = "cuenta_corriente"
    TODOS: list[str] = [EFECTIVO, DIGITAL, CUENTA_CORRIENTE]
