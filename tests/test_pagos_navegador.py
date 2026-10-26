"""Checkout simulado y revisión visual en Chrome, sin cobros externos."""

import os
import subprocess
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from tests.test_regresion_paginas import aplicacion, db
from tests.test_recepcion_bd import envio
from app.controllers.caja_controller import CajaController
from app.services.conciliacion_mp import ConciliacionMP
from app.utils.exceptions import PagoExternoError
from config.settings import MercadoPagoConfig as C
from web.extensions import limiter


@pytest.mark.skipif(not os.getenv("FORMOPACK_TEST_NODE"), reason="Requiere Node/Playwright explícitos")
def test_checkout_y_presentacion(aplicacion, db, monkeypatch):
    monkeypatch.setattr(C, "COLLECTOR_ID", "12345")
    monkeypatch.setattr(C, "TEST_MODE", True)
    registro = envio(db)
    CajaController(db).abrir_turno(2, 100)

    class ProveedorPrueba:
        orden = None
        consultas = 0
        def crear_preferencia(self, guia, descripcion, monto, orden):
            self.orden = orden
            return {"id": "preferencia-browser", "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/test"}
        def buscar_pagos(self, guia):
            self.consultas += 1
            if self.consultas == 1:
                raise PagoExternoError("No se pudo consultar el pago. Reintentando.", 503)
            return ["98765"]
        def obtener_pago(self, payment_id):
            return {"id": 98765, "status": "approved", "transaction_amount": registro["cotizacion"]["costo_total"],
                "collector_id": 12345, "external_reference": registro["nro_guia"], "currency_id": "ARS", "live_mode": False,
                "metadata": {"formopack_orden": self.orden}}

    api = ProveedorPrueba()
    servicio = ConciliacionMP(db, api)
    limiter.reset()
    servidor = make_server("127.0.0.1", 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        with patch("web.routes.recepcion.ConciliacionMP", return_value=servicio):
            resultado = subprocess.run([os.environ["FORMOPACK_TEST_NODE"], str(Path(__file__).parent / "browser/pagos.cjs")],
                env={**os.environ, "FORMOPACK_TEST_URL": f"http://127.0.0.1:{servidor.server_port}", "FORMOPACK_TEST_GUIA": registro["nro_guia"]},
                capture_output=True, text=True, timeout=65)
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM pagos")
            assert cur.fetchone()["total"] == 1
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
        limiter.reset()
