"""Pruebas de consola para autenticación y modelos de usuario."""

import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import RoleConfig
from app.core.database import DatabaseManager
from app.controllers.auth_controller import AuthController
from app.models.usuario import Usuario
from app.utils.exceptions import (
    AuthenticationError,
    DatabaseConnectionError,
    UserInactiveError,
    UserNotFoundError,
    ValidationError,
)

logging.basicConfig(level=logging.WARNING)


def test_hash_password():
    """Prueba hashing Bcrypt y verificación."""
    password = "MiPassword123!"
    hashed = Usuario.hashear_password(password)

    usuario = Usuario(
        id_usuario=0,
        nombre="Test",
        email="test@test.com",
        credenciales_hash=hashed,
        tipo_usuario=RoleConfig.ADMINISTRADOR,
    )
    assert usuario.verificar_password(password)
    assert not usuario.verificar_password("wrong_password")
    print("  [OK] Hash y verificación Bcrypt")


def test_factory_usuario():
    """Prueba fábrica de usuarios según rol."""
    roles = [RoleConfig.ADMINISTRADOR, RoleConfig.RECEPCIONISTA, RoleConfig.CHOFER]
    for tipo in roles:
        fila = {
            "id_usuario": 1,
            "nombre": "Test",
            "email": f"{tipo}@test.com",
            "credenciales_hash": "hash",
            "tipo_usuario": tipo,
            "activo": True,
            "nro_licencia": None,
        }
        u = Usuario.from_db_row(fila)
        assert u.tipo_usuario == tipo

    try:
        Usuario.from_db_row({**fila, "tipo_usuario": "invalido"})
        assert False
    except ValidationError:
        pass
    print("  [OK] Factory Usuario.from_db_row por rol")


def test_validacion_login():
    """Prueba validación de datos de entrada en login."""
    auth = AuthController.__new__(AuthController)
    casos = [("", "pass"), ("sin_arroba", "pass"), ("user@test.com", "")]
    for email, pw in casos:
        try:
            auth._validar_campos_login(email, pw)
            assert False
        except ValidationError:
            pass
    print("  [OK] Validación de campos de login")


def test_conexion_bd() -> bool:
    """Prueba conexión al servidor MySQL (Singleton)."""
    try:
        db1 = DatabaseManager.get_instance()
        db1.test_connection()
        db2 = DatabaseManager.get_instance()
        assert db1 is db2
        print("  [OK] Conexión MySQL y Singleton")
        return True
    except DatabaseConnectionError:
        print("  [INFO] Conexión MySQL omitida (servidor no disponible)")
        return False


def test_login_con_bd():
    """Prueba login contra base de datos activa."""
    auth = AuthController()
    try:
        auth.login("noexiste@formopack.com", "pass")
    except UserNotFoundError:
        print("  [OK] Usuario no registrado detectado")
    except DatabaseConnectionError:
        return


def main():
    print("\n--- Pruebas Sprint 1 (Auth & POO) ---")
    test_hash_password()
    test_factory_usuario()
    test_validacion_login()

    if test_conexion_bd():
        test_login_con_bd()

    print("--- Pruebas finalizadas ---\n")


if __name__ == "__main__":
    main()
