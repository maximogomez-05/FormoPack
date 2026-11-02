"""Despacho y visita desde Chrome, con servidor y base aislados."""
import os
import subprocess
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

from tests.test_regresion_paginas import aplicacion, db
from tests.test_logistica_segura import preparar, sin_correos


@pytest.mark.skipif(not os.getenv('FORMOPACK_TEST_NODE'), reason='Requiere Chrome/Playwright explícitos')
def test_despacho_inicio_fallo_reintento_y_entrega(aplicacion, db):
    ids, movil = preparar(db)
    servidor = make_server('127.0.0.1', 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        resultado = subprocess.run([os.environ['FORMOPACK_TEST_NODE'], str(Path(__file__).parent / 'browser/logistica.cjs')],
            env={**os.environ, 'FORMOPACK_TEST_URL': f'http://127.0.0.1:{servidor.server_port}',
                 'FORMOPACK_TEST_ENVIO': str(ids[0]), 'FORMOPACK_TEST_VEHICULO': str(movil)},
            capture_output=True, text=True, timeout=70)
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        with db.cursor() as cur:
            cur.execute('SELECT estado_actual FROM envios WHERE id_envio=%s', (ids[0],))
            assert cur.fetchone()['estado_actual'] == 'entregado'
            cur.execute('SELECT COUNT(*) AS total FROM hojas_de_ruta WHERE estado=\'cerrada\'')
            assert cur.fetchone()['total'] == 2
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)

@pytest.mark.skipif(not os.getenv('FORMOPACK_TEST_NODE'), reason='Requiere Chrome/Playwright explícitos')
def test_dos_choferes_en_un_dispositivo(aplicacion, db):
    from tests.test_logistica_segura import otro_chofer
    from app.services.operaciones_logisticas import OperacionesLogisticas
    ids, movil = preparar(db)
    otro_chofer(db)
    servicio = OperacionesLogisticas(db)
    ruta = servicio.crear('DES-COMPARTIDA-A', 3, movil, ids, 1)
    servicio.iniciar(3, ruta.id_hoja_ruta)
    servidor = make_server('127.0.0.1', 0, aplicacion, threaded=True)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        resultado = subprocess.run([os.environ['FORMOPACK_TEST_NODE'], str(Path(__file__).parent / 'browser/dispositivo_compartido.cjs')],
            env={**os.environ, 'FORMOPACK_TEST_URL': f'http://127.0.0.1:{servidor.server_port}'},
            capture_output=True, text=True, timeout=90)
        assert resultado.returncode == 0, resultado.stderr
        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS total FROM intentos_entrega WHERE id_hoja_ruta=%s', (ruta.id_hoja_ruta,))
            assert cur.fetchone()['total'] == 1
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
