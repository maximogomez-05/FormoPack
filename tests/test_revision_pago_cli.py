"""La herramienta administrativa no escribe antes de la revisión y confirmación."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.revisar_pago_mp import RevisionPagoCLI


@pytest.mark.parametrize('confirmacion', ['CANCELAR', 'CONFIRMAR'])
def test_cli_solo_concilia_tras_confirmacion(confirmacion, capsys):
    actor = SimpleNamespace(id_usuario=1, tipo_usuario='administrador', debe_cambiar_password=False)
    servicio = MagicMock()
    servicio.previsualizar_revision_legacy.return_value = {'guia': 'GUIA-TEST', 'monto': 500}
    motivo = 'Pago recibido y revisado con el pagador'
    with patch('scripts.revisar_pago_mp.AuthController') as auth, \
         patch('scripts.revisar_pago_mp.ConciliacionMP', return_value=servicio), \
         patch('scripts.revisar_pago_mp.getpass.getpass', return_value='clave-privada'), \
         patch('builtins.input', side_effect=['admin@example.com', motivo, confirmacion]):
        auth.return_value.login.return_value.usuario = actor
        RevisionPagoCLI().ejecutar(['--guia', 'GUIA-TEST', '--pago', '98765'])
    servicio.previsualizar_revision_legacy.assert_called_once_with('98765', 'GUIA-TEST', 1)
    if confirmacion == 'CONFIRMAR':
        servicio.conciliar_revision_legacy.assert_called_once_with('98765', 'GUIA-TEST', 1, motivo)
    else:
        servicio.conciliar_revision_legacy.assert_not_called()
    assert 'clave-privada' not in capsys.readouterr().out


@pytest.mark.parametrize('rol,provisoria', [('recepcionista', False), ('administrador', True)])
def test_cli_rechaza_rol_o_clave_provisoria(rol, provisoria):
    actor = SimpleNamespace(id_usuario=2, tipo_usuario=rol, debe_cambiar_password=provisoria)
    with patch('scripts.revisar_pago_mp.AuthController') as auth, \
         patch('scripts.revisar_pago_mp.ConciliacionMP') as servicio, \
         patch('scripts.revisar_pago_mp.getpass.getpass', return_value='clave'), \
         patch('builtins.input', return_value='operador@example.com'):
        auth.return_value.login.return_value.usuario = actor
        with pytest.raises(ValueError):
            RevisionPagoCLI().ejecutar(['--guia', 'GUIA-TEST', '--pago', '98765'])
    servicio.assert_not_called()
