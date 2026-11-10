"""Recursos PWA y mapas completos en Chrome con proveedores interceptados."""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from time import time
from unittest.mock import patch

import pytest
from PIL import Image

from tests.test_regresion_paginas import aplicacion, db
from web.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_iconos_y_zona_segura_maskable():
    client = create_app().test_client()
    respuesta = client.get('/static/manifest.json', base_url='https://formopackexpress.tech')
    manifest = json.loads(respuesta.data)
    assert manifest['id'] == manifest['start_url'] == '/chofer'
    assert manifest['scope'] == '/'
    assert {i['sizes'] for i in manifest['icons']} == {'192x192', '512x512'}
    for icono in manifest['icons']:
        assert client.get(icono['src']).status_code == 200
        im = Image.open(ROOT / 'web' / icono['src'].lstrip('/'))
        assert im.size == tuple(map(int, icono['sizes'].split('x')))
        if icono['purpose'] == 'maskable':
            # Ningún píxel del símbolo fuera del círculo central seguro (radio 40%).
            for y in range(im.height):
                for x in range(im.width):
                    if (x-256)**2 + (y-256)**2 > 204**2:
                        assert im.getpixel((x,y)) == (0, 68, 129)


@pytest.mark.skipif(not os.getenv('FORMOPACK_TEST_NODE'), reason='Requiere Chrome explícito')
def test_mapas_en_navegador(aplicacion, tmp_path):
    datos = dict(nro_guia='FP-TEST', estado_actual='en_ruta', fecha_creacion=datetime.now(),
                 cantidad_intentos=0, localidad_destino='Clorinda')
    with patch('web.routes.admin._obtener_timeline', return_value=(datos, [])):
        publico = aplicacion.test_client().get('/admin/tracking?guia=FP-TEST')
    (tmp_path/'tracking.html').write_bytes(publico.data)
    with patch('web.routes.admin._obtener_timeline', return_value=({**datos, 'estado_actual': 'entregado'}, [])):
        terminal = aplicacion.test_client().get('/admin/tracking?guia=FP-TEST')
    (tmp_path/'tracking_terminal.html').write_bytes(terminal.data)
    client = aplicacion.test_client()
    with client.session_transaction() as sesion:
        sesion.update(usuario_id=1, version_sesion=0, inicio_sesion=time(), ultima_actividad=time())
    operativo = client.get('/admin/logistica')
    assert operativo.status_code == 200
    (tmp_path/'logistica.html').write_bytes(operativo.data)
    proceso = subprocess.run([os.environ['FORMOPACK_TEST_NODE'], str(ROOT/'tests/browser/cierre_mapas.cjs')],
        env={**os.environ, 'FORMOPACK_HTML_TEST': str(tmp_path)}, capture_output=True, text=True, timeout=90)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
