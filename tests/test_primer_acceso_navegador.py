"""Alta administrativa, primer acceso y navegación con Chrome aislado."""

import os
import subprocess
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

from tests.test_regresion_paginas import aplicacion, db
from web.extensions import limiter


@pytest.mark.skipif(not os.getenv("FORMOPACK_TEST_NODE"), reason="Requiere Node/Playwright explícitos")
def test_alta_primer_acceso_e_interfaz(aplicacion, db):
    limiter.reset()
    servidor = make_server("127.0.0.1", 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        resultado = subprocess.run([os.environ["FORMOPACK_TEST_NODE"], str(Path(__file__).parent / "browser/primer_acceso.cjs")],
            env={**os.environ, "FORMOPACK_TEST_URL": f"http://127.0.0.1:{servidor.server_port}"},
            capture_output=True, text=True, timeout=65)
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        with db.cursor() as cur:
            cur.execute("SELECT debe_cambiar_password,version_sesion FROM usuarios WHERE email='nueva@example.com'")
            assert cur.fetchone() == {"debe_cambiar_password": 0, "version_sesion": 1}
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
        limiter.reset()
