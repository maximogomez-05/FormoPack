"""Registro y rechazo de formulario en Chrome con datos aislados."""

import os
import subprocess
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from tests.test_regresion_paginas import aplicacion, db
from web.extensions import limiter


@pytest.mark.skipif(not os.getenv("FORMOPACK_TEST_NODE"), reason="Requiere Node y Playwright explícitos")
def test_recepcion_en_chromium(aplicacion, db):
    limiter.reset()
    servidor = make_server("127.0.0.1", 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
            resultado = subprocess.run(
                [os.environ["FORMOPACK_TEST_NODE"], str(Path(__file__).parent / "browser/recepcion.cjs")],
                env={**os.environ, "FORMOPACK_TEST_URL": f"http://127.0.0.1:{servidor.server_port}"},
                capture_output=True, text=True, timeout=60)
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        with db.cursor() as cur:
            cur.execute("SELECT es_fragil FROM bultos ORDER BY id_bulto")
            assert [bool(b["es_fragil"]) for b in cur.fetchall()] == [False, True, False]
            cur.execute("SELECT COUNT(*) AS total FROM envios")
            assert cur.fetchone()["total"] == 1
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
        limiter.reset()
