"""Pruebas de consola para autenticación y modelos de usuario."""

import sys
import os
import logging
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_seguridad_bd import db, pool_aislado
from config.settings import RoleConfig
from app.core.database import DatabaseManager
from app.controllers.auth_controller import AuthController
from app.models.usuario import Usuario
from app.utils.exceptions import (
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


def test_conexion_bd(pool_aislado):
    gestor = DatabaseManager.get_instance()
    assert gestor.test_connection()
    assert DatabaseManager.get_instance() is gestor


def test_login_con_bd(db):
    with pytest.raises(UserNotFoundError):
        AuthController(db).login("noexiste@formopack.com", "pass")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
