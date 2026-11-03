"""Checkout Pro simulado: firma, conciliación, errores y concurrencia real SQL."""

import hashlib
import hmac
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock, patch

import pytest
import mysql.connector

from app.core.migrations import MigrationManager
from app.controllers.caja_controller import CajaController
from app.services.conciliacion_mp import ConciliacionMP
from app.services.firma_mercadopago import FirmaMercadoPago
from app.services.mercadopago_service import MercadoPagoService
from app.services.referencia_pago import ReferenciaPagoMP
from app.utils.exceptions import PagoExternoError
from config.settings import MercadoPagoConfig as C
from tests.test_recepcion_bd import envio, cliente
from tests.test_regresion_paginas import aplicacion, db


def test_preferencia_excluye_tarjetas_sin_alterar_busqueda():
    servicio = object.__new__(MercadoPagoService)
    servicio._sdk = MagicMock()
    servicio._sdk.preference().create.return_value = {'status': 201, 'response': {'id': 'test'}}
    servicio.crear_preferencia('GUIA-TEST', 'Envío', 500, 'a' * 32)
    payload = servicio._sdk.preference().create.call_args.args[0]
    assert {t['id'] for t in payload['payment_methods']['excluded_payment_types']} == {'credit_card', 'debit_card', 'prepaid_card'}
    assert payload['external_reference'] == 'FPMP-' + 'a' * 32
    assert payload['metadata']['formopack_orden'] == 'a' * 32
    servicio._sdk.payment().search.return_value = {'status': 200, 'response': {'results': []}}
    assert servicio.buscar_pagos('GUIA-TEST') == []
    assert 'payment_methods' not in servicio._sdk.payment().search.call_args.args[0]


@pytest.fixture(autouse=True)
def configuracion(monkeypatch):
    monkeypatch.setattr(C, "COLLECTOR_ID", "12345")
    monkeypatch.setattr(C, "WEBHOOK_SECRET", "solo-pruebas-mp")
    monkeypatch.setattr(C, "TEST_MODE", True)


def firma(data_id="98765", instante=None, request_id="solicitud-test"):
    ts = str(int(time.time()) if instante is None else instante)
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(C.WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={digest}", "x-request-id": request_id}


@pytest.mark.parametrize("milisegundos", [False, True])
def test_firma_valida(milisegundos):
    instante = 1800000000
    headers = firma(instante=instante * (1000 if milisegundos else 1))
    FirmaMercadoPago(C.WEBHOOK_SECRET, lambda: instante).validar(headers["x-signature"], headers["x-request-id"], "98765")


@pytest.mark.parametrize("defecto", ["firma", "id", "reloj", "request", "duplicado"])
def test_firma_rechazada(defecto):
    h = firma(instante=1800000000)
    data_id, request_id, reloj = "98765", h["x-request-id"], 1800000000
    if defecto == "firma": h["x-signature"] = h["x-signature"][:-1] + "z"
    if defecto == "id": data_id = "1234"
    if defecto == "reloj": reloj += 301
    if defecto == "request": request_id = "otra-solicitud"
    if defecto == "duplicado": h["x-signature"] += ",ts=1800000000"
    with pytest.raises(PagoExternoError) as rechazo:
        FirmaMercadoPago(C.WEBHOOK_SECRET, lambda: reloj).validar(h["x-signature"], request_id, data_id)
    assert rechazo.value.status == 401


def contexto(db):
    registro = envio(db)
    turno = CajaController(db).abrir_turno(2, 100)
    api = MagicMock()
    api.crear_preferencia.return_value = {"id": "preferencia-test", "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/test"}
    servicio = ConciliacionMP(db, api)
    servicio.iniciar(registro["nro_guia"], 2)
    orden = api.crear_preferencia.call_args.args[3]
    pago = {"id": 98765, "status": "approved", "external_reference": registro["nro_guia"],
            "transaction_amount": registro["cotizacion"]["costo_total"], "transaction_amount_refunded": 0,
            "collector_id": 12345, "currency_id": "ARS", "live_mode": False,
            "metadata": {"formopack_orden": orden}}
    api.obtener_pago.return_value = pago
    api.buscar_pagos.return_value = ["98765"]
    return servicio, api, pago, registro, turno


def test_conciliacion_idempotente_y_caja(db):
    servicio, api, pago, registro, turno = contexto(db)
    assert servicio.confirmar("98765")["aprobado"]
    assert servicio.confirmar("98765")["aprobado"]
    assert servicio.verificar(registro["nro_guia"])["aprobado"]
    resumen = CajaController(db).cerrar_turno(turno.id_turno, 2)
    assert resumen["cantidad_operaciones"] == 1
    assert resumen["ingresos_digitales"] == pago["transaction_amount"]


def contexto_sin_metadata(db):
    servicio, api, pago, registro, turno = contexto(db)
    pago["metadata"] = {"hide_payer_information": True}
    pago["order"] = {"id": "45775228463", "type": "mercadopago"}
    comercial = {"id": 45775228463, "external_reference": registro["nro_guia"],
                 "preference_id": "preferencia-test",
                 "payments": [{"id": 98765, "status": "approved"}]}
    api.obtener_orden_comercial.return_value = comercial
    return servicio, api, pago, registro, turno, comercial


def test_pago_real_sin_metadata_se_concilia_por_preferencia_una_sola_vez(db):
    servicio, api, pago, registro, turno, _ = contexto_sin_metadata(db)
    barrera = Barrier(3)
    def confirmar(_):
        barrera.wait(timeout=10)
        return servicio.confirmar("98765")["aprobado"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(confirmar, range(3)))
    assert servicio.verificar(registro["nro_guia"])["aprobado"]
    api.obtener_orden_comercial.assert_called_with("45775228463")
    resumen = CajaController(db).cerrar_turno(turno.id_turno, 2)
    assert resumen["cantidad_operaciones"] == 1
    assert resumen["ingresos_digitales"] == pago["transaction_amount"]


@pytest.mark.parametrize("campo,valor", [
    ("id", 1), ("external_reference", "GUIA-AJENA"),
    ("preference_id", "preferencia-ajena"), ("preference_id", None),
    ("payments", []), ("payments", None),
    ("payments", [{"id": 123, "status": "approved"}]),
    ("payments", [{"id": 98765, "status": "pending"}]),
])
def test_orden_comercial_ajena_o_incompleta_no_acredita(db, campo, valor):
    servicio, _, _, _, _, comercial = contexto_sin_metadata(db)
    comercial[campo] = valor
    with pytest.raises(PagoExternoError):
        servicio.confirmar("98765")
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 0


@pytest.mark.parametrize("campo,valor", [
    ("transaction_amount", 1), ("currency_id", "USD"), ("collector_id", 999),
    ("live_mode", True), ("transaction_amount_refunded", 1),
    ("external_reference", "OTRA-GUIA"),
    ("metadata", {"formopack_orden": "invalida"}),
    ("metadata", {"formopack_orden": "f" * 32}),
    ("order", {"id": "../otra", "type": "mercadopago"}),
])
def test_sin_metadata_conserva_validaciones_del_pago(db, campo, valor):
    servicio, _, pago, _, _, _ = contexto_sin_metadata(db)
    pago[campo] = valor
    with pytest.raises(PagoExternoError):
        servicio.confirmar("98765")
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 0


def test_orden_comercial_temporalmente_no_disponible_permite_reintento(db):
    servicio, api, _, _, _, comercial = contexto_sin_metadata(db)
    api.obtener_orden_comercial.side_effect = PagoExternoError("Temporal", 503)
    with pytest.raises(PagoExternoError) as error:
        servicio.confirmar("98765")
    assert error.value.status == 503
    api.obtener_orden_comercial.side_effect = None
    api.obtener_orden_comercial.return_value = comercial
    assert servicio.confirmar("98765")["aprobado"]


def test_adaptador_consulta_orden_comercial_por_id():
    servicio = object.__new__(MercadoPagoService)
    servicio._sdk = MagicMock()
    servicio._sdk.merchant_order().get.return_value = {"status": 200, "response": {"id": 123}}
    assert servicio.obtener_orden_comercial("123") == {"id": 123}
    servicio._sdk.merchant_order().get.assert_called_once_with("123")


def test_polling_recupera_pago_productivo_sin_metadata(aplicacion, db, monkeypatch):
    servicio, _, pago, registro, _, _ = contexto_sin_metadata(db)
    monkeypatch.setattr(C, "TEST_MODE", False)
    pago["live_mode"] = True
    client, token = cliente(aplicacion)
    with patch("web.routes.recepcion.ConciliacionMP", return_value=servicio):
        for _ in range(2):
            respuesta = client.post("/recepcion/mp/verificar/" + registro["nro_guia"],
                                   headers={"X-CSRFToken": token})
            assert respuesta.status_code == 200
            assert respuesta.json["aprobado"]
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 1


def test_referencia_unica_recupera_pago_con_preferencia_y_aplicacion_derivadas(db):
    servicio, api, pago, registro, turno, _ = contexto_sin_metadata(db)
    orden = api.crear_preferencia.call_args.args[3]
    referencia = ReferenciaPagoMP.crear(orden)
    pago['external_reference'] = referencia
    # Reproduce el recorrido observado: otra preferencia y ninguna metadata propia.
    api.obtener_orden_comercial.return_value['preference_id'] = 'preferencia-derivada'
    api.obtener_orden_comercial.return_value['external_reference'] = referencia
    api.buscar_pagos.side_effect = lambda ref: ['98765'] if ref == referencia else []
    assert servicio.verificar(registro['nro_guia'])['aprobado']
    assert servicio.confirmar('98765')['aprobado']
    api.buscar_pagos.assert_called_once_with(referencia)
    # La identidad es la referencia de orden aleatoria, no la preferencia derivada.
    api.obtener_orden_comercial.assert_not_called()
    assert CajaController(db).cerrar_turno(turno.id_turno, 2)['cantidad_operaciones'] == 1


@pytest.mark.parametrize('defecto', ['otra-orden', 'contradiccion', 'importe', 'receptor', 'moneda', 'modo', 'reembolso'])
def test_referencia_nueva_conserva_controles(db, defecto):
    servicio, api, pago, _, _, _ = contexto_sin_metadata(db)
    orden = api.crear_preferencia.call_args.args[3]
    pago['external_reference'] = ReferenciaPagoMP.crear(orden)
    if defecto == 'otra-orden': pago['external_reference'] = ReferenciaPagoMP.crear('f' * 32)
    if defecto == 'contradiccion': pago['metadata'] = {'formopack_orden': 'f' * 32}
    if defecto == 'importe': pago['transaction_amount'] = 1
    if defecto == 'receptor': pago['collector_id'] = 999
    if defecto == 'moneda': pago['currency_id'] = 'USD'
    if defecto == 'modo': pago['live_mode'] = True
    if defecto == 'reembolso': pago['transaction_amount_refunded'] = 1
    with pytest.raises(PagoExternoError):
        servicio.confirmar('98765')
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS total FROM pagos')
        assert cur.fetchone()['total'] == 0


def contexto_revision(db):
    servicio, api, pago, registro, turno, comercial = contexto_sin_metadata(db)
    comercial['preference_id'] = 'preferencia-derivada'
    api.obtener_preferencia.return_value = {
        'id': 'preferencia-test', 'collector_id': 12345,
        'external_reference': registro['nro_guia'],
        'metadata': {'formopack_orden': api.crear_preferencia.call_args.args[3]},
    }
    return servicio, api, pago, registro, turno


def test_revision_legacy_explicita_y_auditada_no_habilita_acreditacion_automatica(db):
    servicio, _, pago, registro, turno = contexto_revision(db)
    guia = registro['nro_guia']
    with pytest.raises(PagoExternoError):
        servicio.confirmar('98765')
    detalle = servicio.previsualizar_revision_legacy('98765', guia, 1)
    assert detalle['preferencia_cobro'] == 'preferencia-derivada'
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS total FROM pagos')
        assert cur.fetchone()['total'] == 0
    for _ in range(2):
        assert servicio.conciliar_revision_legacy('98765', guia, 1, 'Cobro verificado con el pagador y en cuenta receptora')['aprobado']
    with db.cursor() as cur:
        cur.execute('SELECT * FROM revisiones_pago_mp')
        auditoria = cur.fetchall()
        assert len(auditoria) == 1
        assert auditoria[0]['id_administrador'] == 1
        assert auditoria[0]['preferencia_original'] == 'preferencia-test'
        assert auditoria[0]['preferencia_cobro'] == 'preferencia-derivada'
    resumen = CajaController(db).cerrar_turno(turno.id_turno, 2)
    assert resumen['cantidad_operaciones'] == 1
    assert resumen['ingresos_digitales'] == pago['transaction_amount']


@pytest.mark.parametrize('actor', [2, 3, 999])
def test_revision_solo_administrador_activo(db, actor):
    servicio, api, _, registro, _ = contexto_revision(db)
    with pytest.raises(PagoExternoError) as error:
        servicio.conciliar_revision_legacy('98765', registro['nro_guia'], actor, 'Motivo suficientemente detallado de revisión')
    assert error.value.status == 403
    api.obtener_pago.assert_not_called()


@pytest.mark.parametrize('defecto', ['inactivo', 'pendiente', 'importe', 'receptor', 'moneda', 'modo', 'reembolso',
                                      'guia', 'orden-original', 'preferencia-original', 'receptor-original'])
def test_revision_no_fuerza_pagos_inconsistentes(db, defecto):
    servicio, api, pago, registro, _ = contexto_revision(db)
    if defecto == 'inactivo':
        with db.cursor() as cur: cur.execute('UPDATE usuarios SET activo=0 WHERE id_usuario=1')
    if defecto == 'pendiente': pago['status'] = 'pending'
    if defecto == 'importe': pago['transaction_amount'] = 1
    if defecto == 'receptor': pago['collector_id'] = 999
    if defecto == 'moneda': pago['currency_id'] = 'USD'
    if defecto == 'modo': pago['live_mode'] = True
    if defecto == 'reembolso': pago['transaction_amount_refunded'] = 1
    if defecto == 'guia': pago['external_reference'] = 'GUIA-AJENA'
    if defecto == 'orden-original': api.obtener_preferencia.return_value['metadata'] = {}
    if defecto == 'preferencia-original': api.obtener_preferencia.return_value['id'] = 'preferencia-ajena'
    if defecto == 'receptor-original': api.obtener_preferencia.return_value['collector_id'] = 999
    with pytest.raises(PagoExternoError):
        servicio.conciliar_revision_legacy('98765', registro['nro_guia'], 1, 'Motivo suficientemente detallado de revisión')
    with db.cursor() as cur:
        for tabla in ('pagos', 'revisiones_pago_mp'):
            cur.execute(f'SELECT COUNT(*) AS total FROM {tabla}')
            assert cur.fetchone()['total'] == 0


def test_fallo_auditoria_revierte_cobro_y_permite_reintento(db):
    servicio, _, _, registro, turno = contexto_revision(db)
    with db.cursor(False) as cur:
        cur.execute("CREATE TRIGGER fallo_revision BEFORE INSERT ON revisiones_pago_mp FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
    with pytest.raises(PagoExternoError) as error:
        servicio.conciliar_revision_legacy('98765', registro['nro_guia'], 1, 'Pago recibido y revisado con el cliente')
    assert error.value.status == 503
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS total FROM pagos')
        assert cur.fetchone()['total'] == 0
        cur.execute('DROP TRIGGER fallo_revision')
    CajaController(db).cerrar_turno(turno.id_turno, 2)
    assert servicio.conciliar_revision_legacy('98765', registro['nro_guia'], 1, 'Pago recibido y revisado con el cliente')['aprobado']
    with db.cursor() as cur:
        cur.execute('SELECT id_turno FROM pagos')
        assert cur.fetchone()['id_turno'] is None
    db.ejecutar_archivo(Path(__file__).resolve().parents[1] / 'scripts/migrations/012_revision_pagos_mp.sql')


def revision_confirmada(db):
    servicio, api, pago, registro, turno = contexto_revision(db)
    servicio.conciliar_revision_legacy('98765', registro['nro_guia'], 1,
                                     'Cobro recibido y revisado con el pagador')
    return servicio, api, pago, registro, turno


def test_webhook_reenviado_reconoce_revision_sin_escrituras(aplicacion, db, caplog):
    servicio, _, pago, _, turno = revision_confirmada(db)
    with db.cursor() as cur:
        cur.execute('SELECT * FROM turnos_caja WHERE id_turno=%s', (turno.id_turno,))
        caja_antes = cur.fetchone()
    # Prohibir escrituras demuestra que reconocer un reenvío solo lee el cobro.
    with db.cursor(False) as cur:
        for tabla in ('pagos', 'revisiones_pago_mp'):
            for operacion in ('INSERT', 'UPDATE'):
                cur.execute(f"CREATE TRIGGER no_{tabla}_{operacion} BEFORE {operacion} ON {tabla} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sin escrituras'")
    with patch('web.routes.recepcion.ConciliacionMP', return_value=servicio):
        for _ in range(2):
            respuesta = aplicacion.test_client().post('/recepcion/mp/webhook?data.id=98765',
                json={'type': 'payment', 'data': {'id': '98765'}}, headers=firma())
            assert respuesta.status_code == 200
            assert respuesta.json['aprobado']
            assert respuesta.json['estado'] == 'confirmado'
            assert not respuesta.json.get('revision')
    assert 'Pago externo requiere revisión' not in caplog.text
    with db.cursor() as cur:
        for tabla in ('pagos', 'revisiones_pago_mp'):
            cur.execute(f'SELECT COUNT(*) AS total FROM {tabla}')
            assert cur.fetchone()['total'] == 1
        cur.execute('SELECT * FROM turnos_caja WHERE id_turno=%s', (turno.id_turno,))
        assert cur.fetchone() == caja_antes
        cur.execute('SELECT SUM(monto) AS total FROM pagos WHERE id_turno=%s', (turno.id_turno,))
        assert float(cur.fetchone()['total']) == pago['transaction_amount']


def test_reenvios_concurrentes_conservan_revision_y_arqueo_cerrado(db):
    servicio, _, _, _, turno = revision_confirmada(db)
    resumen = CajaController(db).cerrar_turno(turno.id_turno, 2)
    barrera = Barrier(3)
    def confirmar(_):
        barrera.wait(timeout=10)
        return servicio.confirmar('98765')['aprobado']
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(confirmar, range(3)))
    with db.cursor() as cur:
        cur.execute('SELECT ingresos_digitales,estado_caja FROM turnos_caja WHERE id_turno=%s', (turno.id_turno,))
        fila = cur.fetchone()
        assert fila['estado_caja'] == 'cerrado'
        assert fila['ingresos_digitales'] == resumen['ingresos_digitales']
        for tabla in ('pagos', 'revisiones_pago_mp'):
            cur.execute(f'SELECT COUNT(*) AS total FROM {tabla}')
            assert cur.fetchone()['total'] == 1


@pytest.mark.parametrize('defecto', ['importe', 'receptor', 'moneda', 'modo', 'reembolso', 'referencia',
                                    'otro-id', 'preferencia-cobro', 'preferencia-original', 'sin-auditoria',
                                    'importe-local', 'guia-esperada'])
def test_revision_previa_no_oculta_discrepancias_actuales(db, defecto):
    servicio, api, pago, registro, _ = revision_confirmada(db)
    payment_id, guia = '98765', registro['nro_guia']
    if defecto == 'importe': pago['transaction_amount'] = 1
    if defecto == 'receptor': pago['collector_id'] = 999
    if defecto == 'moneda': pago['currency_id'] = 'USD'
    if defecto == 'modo': pago['live_mode'] = True
    if defecto == 'reembolso': pago['transaction_amount_refunded'] = 1
    if defecto == 'referencia':
        pago['external_reference'] = 'GUIA-AJENA'
        api.obtener_orden_comercial.return_value['external_reference'] = 'GUIA-AJENA'
    if defecto == 'otro-id':
        payment_id = '99999'
        pago['id'] = 99999
        api.obtener_orden_comercial.return_value['payments'] = [{'id': 99999, 'status': 'approved'}]
    if defecto == 'preferencia-cobro': api.obtener_orden_comercial.return_value['preference_id'] = 'otra-preferencia'
    with db.cursor() as cur:
        if defecto == 'preferencia-original':
            cur.execute("UPDATE revisiones_pago_mp SET preferencia_original='otra-preferencia'")
        if defecto == 'sin-auditoria': cur.execute('DELETE FROM revisiones_pago_mp')
        if defecto == 'importe-local': cur.execute('UPDATE pagos SET monto=1')
    if defecto == 'guia-esperada': guia = 'GUIA-AJENA'
    with pytest.raises(PagoExternoError):
        servicio.confirmar(payment_id, guia)
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS total FROM pagos')
        assert cur.fetchone()['total'] == 1


def test_revision_previa_no_anuncia_pago_que_dejo_de_estar_aprobado(db):
    servicio, _, pago, _, _ = revision_confirmada(db)
    pago['status'] = 'refunded'
    assert not servicio.confirmar('98765')['aprobado']


@pytest.mark.parametrize("campo,valor", [
    ("external_reference", "GUIA-AJENA"), ("transaction_amount", 1), ("transaction_amount", "NaN"),
    ("currency_id", "USD"), ("collector_id", 999), ("live_mode", True),
    ("live_mode", None), ("metadata", {}), ("transaction_amount_refunded", 1), ("id", 123),
])
def test_pago_inconsistente_no_se_acredita(db, campo, valor):
    servicio, api, pago, _, _ = contexto(db)
    pago[campo] = valor
    with pytest.raises(PagoExternoError):
        servicio.confirmar("98765")
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 0


def test_otra_guia_en_polling_no_adopta_pago(db):
    servicio, _, _, _, _ = contexto(db)
    with pytest.raises(PagoExternoError):
        servicio.confirmar("98765", "OTRA-GUIA")


def test_pago_pendiente_no_se_acredita(db):
    servicio, _, pago, _, _ = contexto(db)
    pago["status"] = "pending"
    assert not servicio.confirmar("98765")["aprobado"]


def test_webhook_polling_concurrentes_no_duplican(db):
    servicio, _, _, _, _ = contexto(db)
    barrera = Barrier(3)
    def confirmar(_):
        barrera.wait(timeout=10)
        return servicio.confirmar("98765")["aprobado"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(confirmar, range(3)))
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 1


def test_cierre_previo_conserva_arqueo_y_muestra_ingreso_externo(db):
    servicio, _, pago, _, turno = contexto(db)
    CajaController(db).cerrar_turno(turno.id_turno, 2)
    assert servicio.confirmar("98765")["aprobado"]
    assert servicio.listar_sin_turno(1)[0]["monto"] == pago["transaction_amount"]
    with pytest.raises(PagoExternoError): servicio.listar_sin_turno(2)
    with db.cursor() as cur:
        cur.execute("SELECT ingresos_digitales FROM turnos_caja WHERE id_turno=%s", (turno.id_turno,))
        assert cur.fetchone()["ingresos_digitales"] == 0


def test_fallo_sql_no_anuncia_aprobacion_y_permite_reintento(db):
    servicio, _, _, _, _ = contexto(db)
    with db.cursor(False) as cur:
        cur.execute("CREATE TRIGGER fallo_mp BEFORE INSERT ON pagos FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
    with pytest.raises(PagoExternoError) as fallo:
        servicio.confirmar("98765")
    assert fallo.value.status == 503
    with db.cursor(False) as cur:
        cur.execute("DROP TRIGGER fallo_mp")
    assert servicio.confirmar("98765")["aprobado"]


def test_http_webhook_y_retorno_no_confian_en_querystring(aplicacion, db):
    servicio, _, _, registro, _ = contexto(db)
    client = aplicacion.test_client()
    with patch("web.routes.recepcion.ConciliacionMP", return_value=servicio):
        assert client.get("/recepcion/mp/success?status=approved&payment_id=98765").status_code == 200
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM pagos")
            assert cur.fetchone()["total"] == 0
        assert client.post("/recepcion/mp/webhook", json={}).status_code == 401
        r = client.post("/recepcion/mp/webhook?data.id=98765", json={"type": "payment", "data": {"id": "98765"}}, headers=firma())
        assert r.status_code == 200 and r.json["aprobado"]


def test_webhook_error_transitorio_devuelve_503(aplicacion, db):
    with patch("web.routes.recepcion.ConciliacionMP") as cls:
        cls.return_value.confirmar.side_effect = PagoExternoError("Temporal", 503)
        r = aplicacion.test_client().post("/recepcion/mp/webhook?data.id=98765", json={"type": "payment", "data": {"id": "98765"}}, headers=firma())
    assert r.status_code == 503 and not r.json["aprobado"]


def test_polling_exige_post_csrf_y_no_acepta_pago_manual(aplicacion, db):
    servicio, _, _, registro, _ = contexto(db)
    client, token = cliente(aplicacion)
    ruta = "/recepcion/mp/verificar/" + registro["nro_guia"]
    assert client.get(ruta).status_code == 405
    assert client.post(ruta).status_code == 400
    with patch("web.routes.recepcion.ConciliacionMP", return_value=servicio):
        r = client.post(ruta, headers={"X-CSRFToken": token})
    assert r.status_code == 200 and r.json["aprobado"]


def test_sdk_no_oculta_fallo_como_pago_pendiente(monkeypatch):
    monkeypatch.setattr(C, "ACCESS_TOKEN", "TEST-only-for-tests")
    with patch("app.services.mercadopago_service.mercadopago.SDK") as sdk:
        sdk.return_value.payment.return_value.get.return_value = {"status": 500, "response": {}}
        with pytest.raises(PagoExternoError) as fallo:
            MercadoPagoService().obtener_pago("98765")
        assert fallo.value.status == 503


def test_migracion_repetida_y_restriccion_pago_externo(db):
    servicio, _, _, registro, _ = contexto(db)
    servicio.confirmar("98765")
    from tests.test_seguridad_bd import ROOT
    db.ejecutar_archivo(ROOT / "scripts/migrations/007_pagos_mp.sql")
    with pytest.raises(mysql.connector.IntegrityError):
        with db.cursor() as cur:
            cur.execute("INSERT INTO pagos (id_envio,monto,tipo_pago,id_transaccion_ext) VALUES (%s,1,'digital','98765')", (registro["id_envio"],))


def test_preflight_no_modifica_referencias_duplicadas(db):
    servicio, _, _, registro, _ = contexto(db)
    servicio.confirmar("98765")
    with db.cursor() as cur:
        cur.execute("ALTER TABLE pagos DROP INDEX uk_pago_externo")
        cur.execute("INSERT INTO pagos (id_envio,monto,tipo_pago,id_transaccion_ext) VALUES (%s,1,'digital','98765')", (registro["id_envio"],))
        cur.execute("DELETE FROM schema_migrations WHERE version='007_pagos_mp'")
    with pytest.raises(ValueError, match="duplicadas"):
        MigrationManager(db).aplicar_migraciones(desde="007")


def test_pago_manual_no_suplanta_mercadopago(db):
    from app.controllers.envio_controller import EnvioController
    from app.utils.exceptions import ValidationError
    servicio, _, pago, registro, turno = contexto(db)
    with pytest.raises(ValidationError):
        EnvioController(db).registrar_pago(registro["id_envio"], pago["transaction_amount"],
            "digital", turno.id_turno, id_usuario=2, id_transaccion_qr="inventado", billetera_virtual="MercadoPago")


def test_iniciar_exige_caja_y_no_acepta_url_externa(db):
    registro = envio(db)
    api = MagicMock()
    with pytest.raises(PagoExternoError):
        ConciliacionMP(db, api).iniciar(registro["nro_guia"], 2)
    api.crear_preferencia.assert_not_called()
    CajaController(db).abrir_turno(2)
    api.crear_preferencia.return_value = {"id": "pref-test", "sandbox_init_point": "https://ejemplo-malicioso.com/pagar"}
    with pytest.raises(PagoExternoError):
        ConciliacionMP(db, api).iniciar(registro["nro_guia"], 2)


def test_reabrir_checkout_reutiliza_la_preferencia(db):
    servicio, api, _, registro, _ = contexto(db)
    assert servicio.iniciar(registro["nro_guia"], 2)["url_checkout"].startswith("https://sandbox.")
    api.crear_preferencia.assert_called_once()


@pytest.mark.parametrize("verificada", [False, True])
def test_transferencia_manual_exige_confirmacion_y_no_se_presenta_como_mp(aplicacion, db, verificada):
    registro = envio(db)
    CajaController(db).abrir_turno(2)
    client, token = cliente(aplicacion)
    datos = {"csrf_token": token, "tipo_pago": "digital", "monto": registro["cotizacion"]["costo_total"],
        "id_transaccion_qr": "BANCO-PRUEBA-0001", "billetera_virtual": "Transferencia Bancaria"}
    if verificada:
        datos["transferencia_verificada"] = "1"
    respuesta = client.post("/recepcion/cobrar/" + registro["nro_guia"], data=datos)
    assert respuesta.status_code == (302 if verificada else 400)
    with db.cursor() as cur:
        cur.execute("SELECT billetera_virtual,id_transaccion_ext FROM pagos")
        pagos = cur.fetchall()
        assert len(pagos) == (1 if verificada else 0)
        if verificada:
            assert pagos[0] == {"billetera_virtual": "Transferencia Bancaria", "id_transaccion_ext": None}

def test_diagnostico_firma_no_expone_credenciales(caplog):
    secreto = "secreto-privado-de-prueba"
    encabezado = "ts=1800000000,v1=" + "0" * 64
    with pytest.raises(PagoExternoError):
        FirmaMercadoPago(secreto, lambda: 1800000000).validar(
            encabezado, "solicitud-privada", "98765"
        )
    assert "HMAC distinto al esperado" in caplog.text
    for privado in (secreto, encabezado, "solicitud-privada", "98765"):
        assert privado not in caplog.text

@pytest.mark.parametrize("estado", [401,403,429,500,503])
def test_error_api_conserva_reintento_sin_exponer_respuesta(estado, caplog):
    servicio = object.__new__(MercadoPagoService)
    servicio._sdk = MagicMock()
    servicio._sdk.payment().get.return_value = {"status":estado,"response":{"message":"detalle-privado"}}
    with pytest.raises(PagoExternoError) as error:
        servicio.obtener_pago("98765")
    assert error.value.status == 503
    assert f"HTTP {estado}" in caplog.text
    assert "detalle-privado" not in caplog.text


def test_pago_inexistente_es_distinto_de_caida_del_proveedor():
    servicio = object.__new__(MercadoPagoService)
    servicio._sdk = MagicMock()
    servicio._sdk.payment().get.return_value = {"status":404,"response":{"message":"Payment not found"}}
    with pytest.raises(PagoExternoError) as error:
        servicio.obtener_pago("123456")
    assert error.value.status == 404
    assert error.value.code == "PAYMENT_NOT_FOUND"
