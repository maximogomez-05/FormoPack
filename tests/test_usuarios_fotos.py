"""Fotos de las tarjetas de administración, sin acceder a la base configurada."""
from time import time
from unittest.mock import patch

import pytest

from app.core.database import DatabaseManager
from tests.test_seguridad_http import app


def sesion(client, rol):
    DatabaseManager.get_instance.return_value.get_connection.return_value.cursor.return_value.fetchone.return_value = {
        'activo': 1, 'version_sesion': 0, 'tipo_usuario': rol,
        'nombre': 'Operador', 'email': 'operador@example.com',
    }
    with client.session_transaction() as datos:
        datos.update(usuario_id=1, rol=rol, version_sesion=0,
                     inicio_sesion=time(), ultima_actividad=time())


def test_tarjetas_muestran_foto_si_existe_e_inicial_si_no(app):
    client = app.test_client()
    sesion(client, 'administrador')
    usuarios = [dict(id_usuario=identificador, nombre=nombre, email='a@example.com',
                     tipo_usuario='chofer', activo=1, tiene_foto=con_foto)
                for identificador, nombre, con_foto in [(2, 'Ana', 1), (3, 'Bruno', 0)]]
    with patch('web.routes.admin.UsuarioController') as ctrl:
        ctrl.return_value.listar_usuarios.return_value = usuarios
        respuesta = client.get('/admin/usuarios')
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert '/admin/usuarios/2/foto' in html
    assert '/admin/usuarios/3/foto' not in html
    assert '<span>B</span>' in html


@pytest.mark.parametrize('imagen,estado', [(b'contenido-png', 200), (None, 404)])
def test_foto_admin_sin_cache(app, imagen, estado):
    client = app.test_client()
    sesion(client, 'administrador')
    with patch('web.routes.admin.PerfilUsuario') as servicio:
        servicio.return_value.foto.return_value = imagen
        respuesta = client.get('/admin/usuarios/2/foto')
        servicio.return_value.foto.assert_called_once_with(2)
    assert respuesta.status_code == estado
    assert respuesta.data == (imagen or b'')
    assert 'no-store' in respuesta.headers['Cache-Control']


@pytest.mark.parametrize('rol', [None, 'recepcionista', 'chofer'])
def test_fotos_de_otras_cuentas_solo_para_admin(app, rol):
    client = app.test_client()
    if rol:
        sesion(client, rol)
    with patch('web.routes.admin.PerfilUsuario') as servicio:
        respuesta = client.get('/admin/usuarios/2/foto')
        servicio.assert_not_called()
    assert respuesta.status_code == (403 if rol else 302)
