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
