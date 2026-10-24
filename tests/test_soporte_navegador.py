"""Flujo real de navegador opt-in, aislado de los datos operativos."""

import os
import subprocess
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from tests.test_seguridad_bd import db
from web.app import create_app
from web.extensions import limiter

pytestmark = pytest.mark.skipif(not os.getenv("FORMOPACK_TEST_NODE"), reason="Requiere Node y Playwright explícitos")


def test_flujo_soporte_en_chromium(db, tmp_path):
    with patch("app.core.database.DatabaseManager.get_instance", return_value=db), patch("web.app.ROOT", str(tmp_path)):
        app = create_app()
        app.config.update(SESSION_COOKIE_SECURE=False)
        limiter.reset()
        servidor = make_server("127.0.0.1", 0, app, threaded=True)
        hilo = Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            resultado = subprocess.run(
                [os.environ["FORMOPACK_TEST_NODE"], str(Path(__file__).parent / "browser/soporte.cjs")],
                env={**os.environ, "FORMOPACK_TEST_URL": f"http://127.0.0.1:{servidor.server_port}"},
                capture_output=True, text=True, timeout=60,
            )
            assert resultado.returncode == 0, resultado.stdout + resultado.stderr
            assert "flujo completo verificado" in resultado.stdout
            with db.cursor() as cur:
                cur.execute("SELECT estado, id_usuario_cierre FROM chats_soporte")
                chats = cur.fetchall()
                assert len(chats) == 1 and chats[0]["estado"] == "cerrado"
                assert chats[0]["id_usuario_cierre"] == 2
                cur.execute("SELECT COUNT(*) AS total FROM mensajes_soporte")
                assert cur.fetchone()["total"] == 0
        finally:
            servidor.shutdown()
            hilo.join(timeout=5)
            limiter.reset()
