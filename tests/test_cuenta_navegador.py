"""Recorridos de cuenta con navegador y servidor locales."""
import os
import subprocess
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

from app.services.datos_demostracion import DatosDemostracion
from tests.test_perfil import foto_png
from tests.test_regresion_paginas import aplicacion, db
from web.extensions import limiter


@pytest.mark.skipif(not os.getenv("FORMOPACK_TEST_NODE"), reason="Requiere navegador explícito")
@pytest.mark.parametrize("escenario", ["sesiones", "perfil"])
def test_cuenta_en_navegador(aplicacion, db, escenario, tmp_path):
    DatosDemostracion(db).cargar(1)
    foto = tmp_path / "avatar.png"
    foto.write_bytes(foto_png())
    limiter.reset()
    servidor = make_server("127.0.0.1", 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        subprocess.run([os.environ["FORMOPACK_TEST_NODE"], str(Path(__file__).parent / "browser" / (escenario + ".cjs"))],
            env={**os.environ, "FORMOPACK_TEST_URL": f"http://127.0.0.1:{servidor.server_port}",
                 "FORMOPACK_TEST_FOTO": str(foto)}, check=True, timeout=90)
    finally:
        servidor.shutdown()
        hilo.join()
        limiter.reset()
