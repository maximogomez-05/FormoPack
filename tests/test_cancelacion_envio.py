from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.models.estado_envio import EstadoEnvio
from app.services.operaciones_logisticas import OperacionesLogisticas
from app.utils.exceptions import ValidationError


def test_cancelar_pendiente_registra_estado_y_motivo():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"id_envio": 8, "estado_actual": "recibido", "id_hoja_ruta": None, "nro_guia": "FP-8"},
        None,
        None,
        None,
    ]
    operaciones = OperacionesLogisticas(MagicMock())

    @contextmanager
    def transaccion():
        yield cursor

    with patch.object(operaciones, "_transaccion", transaccion), \
         patch.object(operaciones, "_actor"), \
         patch.object(operaciones, "_historial") as historial, \
         patch.object(operaciones, "_avisar") as avisar:
        operaciones.cancelar_envio(8, 3, "Solicitud del remitente")

    assert any("UPDATE envios SET estado_actual='cancelado'" in llamada.args[0]
        for llamada in cursor.execute.call_args_list)
    historial.assert_called_once_with(cursor, 8, "cancelado", 3, "Administración", "Envío cancelado: Solicitud del remitente")
    avisar.assert_called_once()
    assert "cancelado" in EstadoEnvio.TERMINALES


def test_no_cancelar_envio_con_pago_registrado():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"id_envio": 8, "estado_actual": "recibido", "id_hoja_ruta": None, "nro_guia": "FP-8"},
        {"id_pago": 4},
    ]
    operaciones = OperacionesLogisticas(MagicMock())

    @contextmanager
    def transaccion():
        yield cursor

    with patch.object(operaciones, "_transaccion", transaccion), patch.object(operaciones, "_actor"):
        with pytest.raises(ValidationError, match="pago registrado"):
            operaciones.cancelar_envio(8, 3, "Solicitud del remitente")

    assert not any("UPDATE envios SET estado_actual='cancelado'" in llamada.args[0]
        for llamada in cursor.execute.call_args_list)