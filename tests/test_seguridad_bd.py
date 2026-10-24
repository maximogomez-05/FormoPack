"""Integración opt-in en una instancia desechable, nunca en la base configurada.

FORMOPACK_TEST_DB_PORT debe apuntar a una instancia local exclusiva de pruebas.
Se crea una base con nombre aleatorio y se elimina solamente esa base al salir.
"""

import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

import mysql.connector
import pytest

from app.controllers.auth_controller import AuthController
from app.controllers.usuario_controller import UsuarioController
from app.core.migrations import MigrationManager
from app.models.usuario import Usuario
from app.utils.exceptions import ValidationError
from web.security.sesiones import ControlSesion

ROOT = Path(__file__).resolve().parents[1]


class BasePrueba:
    def __init__(self, port, nombre):
        self.port, self.nombre = port, nombre

    def get_connection(self):
        return mysql.connector.connect(host="127.0.0.1", port=self.port, user="root", database=self.nombre)

    @contextmanager
    def cursor(self, dictionary=True):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=dictionary)
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def ejecutar_archivo(self, path):
        sql = path.read_text(encoding="utf-8").replace("formopack_db", self.nombre)
        with self.cursor(False) as cur:
            for sentencia in sql.split(";"):
                if sentencia.strip():
                    cur.execute(sentencia.strip())
                    if cur.with_rows:
                        cur.fetchall()


@pytest.fixture
def db():
    port = os.getenv("FORMOPACK_TEST_DB_PORT")
    if not port:
        pytest.skip("Requiere una instancia desechable explícita: FORMOPACK_TEST_DB_PORT")
    if not port.isdigit() or not 1024 < int(port) < 65536 or int(port) == 3306:
        pytest.fail("Puerto de pruebas inválido: no usar la instancia habitual")
    nombre = "formopack_test_" + uuid.uuid4().hex
    assert re.fullmatch(r"formopack_test_[0-9a-f]{32}", nombre)
    admin = mysql.connector.connect(host="127.0.0.1", port=int(port), user="root")
    cursor = admin.cursor()
    cursor.execute(f"CREATE DATABASE `{nombre}`")
    instancia = BasePrueba(int(port), nombre)
    try:
        # Versión previa al incremento y luego migración real de seguridad.
        instancia.ejecutar_archivo(ROOT / "scripts/migrations/001_init_database.sql")
        instancia.ejecutar_archivo(ROOT / "scripts/migrations/004_recuperacion_contrasenas.sql")
        with instancia.cursor() as cur:
            cur.execute("INSERT INTO recuperacion_contrasenas (id_usuario, codigo, expira_en) VALUES (1, '654321', NOW() + INTERVAL 15 MINUTE)")
        MigrationManager(instancia).aplicar_migraciones(desde="005")
        yield instancia
    finally:
        cursor.execute(f"DROP DATABASE `{nombre}`")
        cursor.close()
        admin.close()


class TestSeguridadPersistente:
    @staticmethod
    def emitir(db):
        with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async") as correo:
            AuthController(db).solicitar_recuperacion("admin@formopack.com")
        return correo.call_args.args[2]

    def test_migracion_invalida_legacy_y_se_puede_repetir(self, db):
        with db.cursor() as cur:
            cur.execute("SELECT codigo, utilizado FROM recuperacion_contrasenas")
            assert all(fila["codigo"] == "" and fila["utilizado"] for fila in cur.fetchall())
        codigo = self.emitir(db)
        # Reejecutar SQL no debe invalidar los OTP nuevos ni restablecer claves.
        db.ejecutar_archivo(ROOT / "scripts/migrations/005_seguridad_acceso.sql")
        assert AuthController(db).restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")

    def test_solo_persiste_hash_y_cambia_password(self, db):
        codigo = self.emitir(db)
        with db.cursor() as cur:
            cur.execute("SELECT codigo, codigo_hash FROM recuperacion_contrasenas WHERE utilizado = 0")
            fila = cur.fetchone()
            assert fila["codigo"] == "" and len(fila["codigo_hash"]) == 64
            assert fila["codigo_hash"] != codigo
        ctrl = AuthController(db)
        assert ctrl.restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")
        assert ctrl.login("admin@formopack.com", "ClaveNueva123").usuario.version_sesion == 1
        with pytest.raises(ValidationError):
            ctrl.restablecer_password("admin@formopack.com", codigo, "OtraClave123", "OtraClave123")

    def test_quinto_error_persiste_y_bloquea_codigo_correcto(self, db):
        codigo = self.emitir(db)
        incorrecto = "000000" if codigo != "000000" else "000001"
        for i in range(5):
            with pytest.raises(ValidationError):
                AuthController(db).restablecer_password("admin@formopack.com", incorrecto, "ClaveNueva123", "ClaveNueva123")
        with pytest.raises(ValidationError):
            AuthController(db).restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")
        with db.cursor() as cur:
            cur.execute("SELECT intentos_fallidos, utilizado FROM recuperacion_contrasenas WHERE codigo_hash IS NOT NULL")
            fila = cur.fetchone()
            assert fila["intentos_fallidos"] == 5 and fila["utilizado"]

    def test_emision_concurrente_respeta_cooldown(self, db):
        barrera = Barrier(6)
        enviados = []
        lock = Lock()

        def enviar(*args):
            with lock:
                enviados.append(args)

        def solicitar(_):
            barrera.wait(timeout=10)
            AuthController(db).solicitar_recuperacion("admin@formopack.com")

        with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async", side_effect=enviar):
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(solicitar, range(6)))
        assert len(enviados) == 1
        with db.cursor() as cur:
            cur.execute("SELECT solicitudes FROM limites_recuperacion")
            assert cur.fetchone()["solicitudes"] == 1

    def test_consumo_concurrente_solo_un_cambio(self, db):
        codigo = self.emitir(db)
        barrera = Barrier(2)

        def consumir(_):
            barrera.wait(timeout=10)
            try:
                return AuthController(db).restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")
            except ValidationError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(consumir, range(2))) == [False, True]

    def test_errores_concurrentes_no_superan_presupuesto(self, db):
        codigo = self.emitir(db)
        incorrecto = "000000" if codigo != "000000" else "000001"
        barrera = Barrier(6)

        def fallar(_):
            barrera.wait(timeout=10)
            with pytest.raises(ValidationError):
                AuthController(db).restablecer_password("admin@formopack.com", incorrecto, "ClaveNueva123", "ClaveNueva123")

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(fallar, range(6)))
        with db.cursor() as cur:
            cur.execute("SELECT intentos_fallidos FROM recuperacion_contrasenas WHERE codigo_hash IS NOT NULL")
            assert cur.fetchone()["intentos_fallidos"] == 5

    def test_restablecer_revoca_sesion_previa(self, db):
        from flask import Flask, session

        app = Flask(__name__)
        app.secret_key = "solo-pruebas"
        codigo = self.emitir(db)
        with app.test_request_context():
            session.update(usuario_id=1, version_sesion=0)
            assert ControlSesion(db).validar()
            AuthController(db).restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")
            assert ControlSesion(db).validar() is False

    def test_cinco_emisiones_por_hora_no_resetean_presupuesto(self, db):
        self.emitir(db)
        for i in range(4):
            with db.cursor() as cur:
                cur.execute("UPDATE limites_recuperacion SET ultimo_envio = NOW() - INTERVAL 2 MINUTE")
            self.emitir(db)
        with db.cursor() as cur:
            cur.execute("UPDATE limites_recuperacion SET ultimo_envio = NOW() - INTERVAL 2 MINUTE")
        with patch("app.controllers.auth_controller.enviar_codigo_recuperacion_async") as correo:
            AuthController(db).solicitar_recuperacion("admin@formopack.com")
        correo.assert_not_called()
        with db.cursor() as cur:
            cur.execute("SELECT solicitudes FROM limites_recuperacion")
            assert cur.fetchone()["solicitudes"] == 5

    def test_desactivar_y_reactivar_no_revalida_sesion_anterior(self, db):
        from flask import Flask, session

        app = Flask(__name__)
        app.secret_key = "solo-pruebas"
        with patch("app.controllers.usuario_controller.DatabaseManager.get_instance", return_value=db):
            assert UsuarioController().toggle_activo(2, 1) is False
            assert UsuarioController().toggle_activo(2, 1) is True
        with app.test_request_context():
            session.update(usuario_id=2, version_sesion=0)
            assert ControlSesion(db).validar() is False

    def test_inicializacion_no_reemplaza_password_modificada(self, db):
        codigo = self.emitir(db)
        AuthController(db).restablecer_password("admin@formopack.com", codigo, "ClaveNueva123", "ClaveNueva123")
        db.ejecutar_archivo(ROOT / "scripts/init_database.sql")
        assert AuthController(db).login("admin@formopack.com", "ClaveNueva123").success
