"""Checkout Pro simulado: firma, conciliación, errores y concurrencia real SQL."""

import hashlib
import hmac
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock, patch

import pytest
import mysql.connector

from app.core.migrations import MigrationManager
from app.controllers.caja_controller import CajaController
from app.services.conciliacion_mp import ConciliacionMP
from app.services.firma_mercadopago import FirmaMercadoPago
from app.services.mercadopago_service import MercadoPagoService
from app.utils.exceptions import PagoExternoError
from config.settings import MercadoPagoConfig as C
from tests.test_recepcion_bd import envio, cliente
from tests.test_regresion_paginas import aplicacion, db


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
