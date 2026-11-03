"""Privacidad de archivos, documentos internos y seguimiento público."""

import io
import re
import uuid
from pathlib import Path

import pytest

from app.services.almacen_evidencias import AlmacenEvidencias
from app.services.operaciones_logisticas import OperacionesLogisticas
from app.services.tracking_publico import TrackingPublico
from tests.test_evidencia_entrega import png, firma_prueba
from tests.test_logistica_segura import preparar, sin_correos
from tests.test_regresion_paginas import aplicacion, db


def sesion(app, usuario):
    cliente = app.test_client()
    if usuario:
        with cliente.session_transaction() as datos:
            datos.update(usuario_id=usuario, version_sesion=0)
    return cliente


def evidencia(app, db, antigua=False):
    # El archivo antiguo debe existir bajo el static real de esta app de pruebas.
    app.static_folder = str(Path(app.config['POD_LEGACY_DIR']).parent.parent)
    ids, vehiculo = preparar(db)
    servicio = OperacionesLogisticas(db)
    hoja = servicio.crear('DES-PRIVACIDAD', 3, vehiculo, ids, 1)
    servicio.iniciar(3, hoja.id_hoja_ruta)
    almacen = AlmacenEvidencias(app.config['POD_UPLOAD_DIR'], app.config['POD_LEGACY_DIR'])
    if antigua:
        carpeta = Path(app.config['POD_LEGACY_DIR'])
        carpeta.mkdir(parents=True)
        (carpeta / 'foto_historica.png').write_bytes(png())
        clave = 'uploads/pod/foto_historica.png'
    else:
        clave = almacen.guardar(ids[0], '.png', png())
    servicio.entregar(3, hoja.id_hoja_ruta, ids[0], 'entregado',
        dni_receptor='12345678', firma_receptor=firma_prueba(), foto_remito=clave)
    with db.cursor() as cur:
        cur.execute('SELECT id_intento FROM intentos_entrega WHERE id_envio=%s', (ids[0],))
        intento = cur.fetchone()['id_intento']
        cur.execute('SELECT nro_guia FROM envios WHERE id_envio=%s', (ids[0],))
        guia = cur.fetchone()['nro_guia']
    return intento, clave, guia


@pytest.mark.parametrize('antigua', [False, True])
@pytest.mark.parametrize('usuario,estado', [(None,302), (3,403), (1,200), (2,200)])
def test_foto_y_firma_solo_personal_autorizado(aplicacion, db, antigua, usuario, estado):
    intento, clave, guia = evidencia(aplicacion, db, antigua)
    cliente = sesion(aplicacion, usuario)
    for tipo in ('foto', 'firma'):
        respuesta = cliente.get(f'/documentos/evidencias/{intento}/{tipo}')
        assert respuesta.status_code == estado
        if estado == 200:
            assert respuesta.mimetype == 'image/png'
            assert respuesta.data.startswith(b'\x89PNG')
            assert 'attachment;' in respuesta.headers['Content-Disposition']
            assert 'no-store' in respuesta.headers['Cache-Control']
            assert 'ETag' not in respuesta.headers
    # Ni la ruta antigua ni una variante codificada pueden servir el archivo.
    for ruta in ('/static/' + clave, '/static/%75ploads/pod/' + clave.rsplit('/',1)[1]):
        assert cliente.get(ruta).status_code == 404
    if estado == 200:
        pagina = cliente.get('/recepcion/comprobante/' + guia)
        assert pagina.status_code == 200
        assert f'/documentos/evidencias/{intento}/foto' in pagina.get_data(as_text=True)
        assert 'data:image/png;base64' not in pagina.get_data(as_text=True)


@pytest.mark.parametrize('usuario,estado', [(None,302), (3,403), (1,200), (2,200)])
def test_documentos_financieros_y_despacho_tienen_rol(aplicacion, db, usuario, estado):
    _, _, guia = evidencia(aplicacion, db)
    cliente = sesion(aplicacion, usuario)
    for sufijo in ('', '/pdf', '/documentos', '/etiqueta'):
        respuesta = cliente.get('/recepcion/comprobante/' + guia + sufijo)
        assert respuesta.status_code == estado
        assert 'no-store' in respuesta.headers['Cache-Control']
        if estado == 200 and sufijo:
            assert respuesta.data.startswith(b'%PDF')
    if usuario in (None, 3):
        assert cliente.get('/admin/retornos/1/constancia').status_code == estado


def test_privados_inexistentes_o_claves_manipuladas_no_exponen_archivos(aplicacion, db):
    intento, _, _ = evidencia(aplicacion, db)
    cliente = sesion(aplicacion, 1)
    for clave in ('../../.env', '/etc/passwd', 'uploads/pod/../../.env', 'uploads/pod/..\\.env'):
        with db.cursor() as cur:
            cur.execute('UPDATE intentos_entrega SET foto_remito=%s WHERE id_intento=%s', (clave,intento))
        respuesta = cliente.get(f'/documentos/evidencias/{intento}/foto')
        assert respuesta.status_code == 404
    assert cliente.get('/documentos/evidencias/999999/firma').status_code == 404
    assert cliente.get(f'/documentos/evidencias/{intento}/inventado').status_code == 404
    with db.cursor() as cur:
        cur.execute("UPDATE intentos_entrega SET firma_receptor='data:image/svg+xml;base64,YQ==' WHERE id_intento=%s", (intento,))
    assert cliente.get(f'/documentos/evidencias/{intento}/firma').status_code == 404


def test_sesion_revocada_no_descarga_evidencia(aplicacion, db):
    intento, _, _ = evidencia(aplicacion, db)
    cliente = sesion(aplicacion, 2)
    with db.cursor() as cur: cur.execute('UPDATE usuarios SET version_sesion=version_sesion+1 WHERE id_usuario=2')
    respuesta = cliente.get(f'/documentos/evidencias/{intento}/foto')
    assert respuesta.status_code in (302,401)
    assert not respuesta.data.startswith(b'\x89PNG')


def test_subida_real_privada_reintento_y_limpieza(aplicacion, db):
    ids, vehiculo = preparar(db)
    s = OperacionesLogisticas(db)
    hoja = s.crear('DES-SUBIDA-PRIVADA', 3, vehiculo, ids, 1)
    s.iniciar(3, hoja.id_hoja_ruta)
    cliente = sesion(aplicacion, 3)
    panel = cliente.get('/chofer').get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', panel).group(1)
    ruta = f'/chofer/hojas/{hoja.id_hoja_ruta}/envios/{ids[0]}/entrega'
    clave = uuid.uuid4().hex
    for _ in range(2):
        respuesta = cliente.post(ruta, data={'csrf_token':token, 'tipo_intento':'entregado',
            'dni_receptor':'12345678', 'firma_receptor':firma_prueba(),
            'foto_remito':(io.BytesIO(png()), 'remito.png')},
            headers={'X-Offline-Sync':'1', 'X-Offline-Key':clave})
        assert respuesta.status_code == 200, respuesta.get_data(as_text=True)
        assert respuesta.json['ok']
    archivos = list(Path(aplicacion.config['POD_UPLOAD_DIR']).glob('*.png'))
    assert len(archivos) == 1
    assert not Path(aplicacion.config['POD_LEGACY_DIR']).exists()
    with db.cursor() as cur:
        cur.execute('SELECT foto_remito FROM intentos_entrega')
        filas = cur.fetchall()
        assert len(filas) == 1
        assert filas[0]['foto_remito'].endswith(archivos[0].name)


def test_subida_rechazada_no_deja_foto_huerfana(aplicacion, db):
    ids, vehiculo = preparar(db)
    s = OperacionesLogisticas(db)
    hoja = s.crear('DES-SIN-INICIAR', 3, vehiculo, ids, 1)
    cliente = sesion(aplicacion, 3)
    panel = cliente.get('/chofer').get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', panel).group(1)
    respuesta = cliente.post(f'/chofer/hojas/{hoja.id_hoja_ruta}/envios/{ids[0]}/entrega',
        data={'csrf_token':token, 'tipo_intento':'entregado', 'dni_receptor':'12345678',
              'firma_receptor':firma_prueba(), 'foto_remito':(io.BytesIO(png()), 'remito.png')},
        headers={'X-Offline-Sync':'1'})
    assert respuesta.status_code == 400
    assert list(Path(aplicacion.config['POD_UPLOAD_DIR']).glob('*.png')) == []


def test_tracking_y_constancia_publica_no_contienen_datos_privados(aplicacion, db):
    intento, _, guia = evidencia(aplicacion, db)
    with db.cursor() as cur:
        cur.execute("UPDATE clientes SET nombre_completo=CONCAT('Privado Unico ',id_cliente),email='secreto@example.com'")
        cur.execute("UPDATE envios SET direccion_destino='DOMICILIO_PRIVADO_357' WHERE nro_guia=%s", (guia,))
        cur.execute("UPDATE historial_estados SET ubicacion='DOMICILIO_PRIVADO_357',observacion='NOTA_PRIVADA_123'")
        cur.execute("UPDATE intentos_entrega SET coordenadas_gps='-23.987654,-58.876543' WHERE id_intento=%s", (intento,))
    cliente = aplicacion.test_client()
    for ruta in ('/admin/tracking?guia=' + guia, '/admin/tracking/descargar-comprobante?guia=' + guia):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200
        texto = respuesta.get_data(as_text=True)
        for privado in ('Privado Unico', 'secreto@example.com', 'DOMICILIO_PRIVADO_357', 'NOTA_PRIVADA_123',
                        '-23.987654', '-58.876543', 'data:image/png;base64', '12345678'):
            assert privado not in texto
        assert guia in texto


def test_tracking_minimo_conserva_gps_solo_en_ruta():
    envio = {'nro_guia':'GUIA', 'estado_actual':'en_ruta', 'remitente':'Ana Pérez',
             'destinatario':'Luis Gómez', 'ubicacion_gps':{'latitud':-26,'longitud':-58},
             'direccion_destino':'Casa privada', 'costo_total':500}
    publico, _ = TrackingPublico.preparar(envio, [])
    assert publico['ubicacion_gps'] == envio['ubicacion_gps']
    assert publico['remitente'] == 'A. P.'
    assert 'direccion_destino' not in publico and 'costo_total' not in publico
    envio['estado_actual'] = 'entregado'
    assert TrackingPublico.preparar(envio, [])[0]['ubicacion_gps'] is None


def test_almacen_rechaza_enlace_simbolico_fuera_de_la_carpeta(tmp_path):
    privado = tmp_path / 'privado'
    privado.mkdir()
    secreto = tmp_path / 'secreto.png'
    secreto.write_bytes(b'privado')
    try:
        (privado / 'foto.png').symlink_to(secreto)
    except OSError:
        pytest.skip('El sistema no permite crear enlaces simbólicos sin privilegios')
    with pytest.raises(FileNotFoundError):
        AlmacenEvidencias(privado).localizar('uploads/pod/foto.png')
