"""Carga de usuarios iniciales de prueba en la base de datos."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from config.settings import RoleConfig

USUARIOS_PRUEBA = [
    {
        "nombre": "Administrador Sistema",
        "email": "admin@formopack.com",
        "password": "admin123",
        "tipo_usuario": RoleConfig.ADMINISTRADOR,
        "nro_licencia": None,
    },
    {
        "nombre": "Maria Recepcionista",
        "email": "recepcion@formopack.com",
        "password": "recep456",
        "tipo_usuario": RoleConfig.RECEPCIONISTA,
        "nro_licencia": None,
    },
    {
        "nombre": "Carlos Chofer",
        "email": "chofer@formopack.com",
        "password": "chofer789",
        "tipo_usuario": RoleConfig.CHOFER,
        "nro_licencia": "LI-123456",
    },
]

SQL_INSERT = """
    INSERT INTO usuarios (nombre, email, credenciales_hash, tipo_usuario, nro_licencia, activo)
    VALUES (%s, %s, %s, %s, %s, 1)
    ON DUPLICATE KEY UPDATE
        credenciales_hash = VALUES(credenciales_hash),
        tipo_usuario = VALUES(tipo_usuario);
"""


def main():
    db = DatabaseManager.get_instance()
    conn = db.get_connection()
    cursor = conn.cursor()

    for u in USUARIOS_PRUEBA:
        hashed = Usuario.hashear_password(u["password"])
        cursor.execute(
            SQL_INSERT,
            (u["nombre"], u["email"], hashed, u["tipo_usuario"], u["nro_licencia"]),
        )
        print(f"  [OK] Usuario: {u['email']} ({u['tipo_usuario']})")

    conn.commit()
    cursor.close()
    conn.close()
    print("Usuarios de prueba listos.")


if __name__ == "__main__":
    main()
