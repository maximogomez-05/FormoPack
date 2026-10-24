"""Recepción y caja con MariaDB aislada y fallos controlados."""

import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest

from app.controllers.caja_controller import CajaController
from app.controllers.envio_controller import EnvioController
from app.controllers.cliente_controller import ClienteController
from app.utils.exceptions import DatabaseQueryError, TurnoCajaError, ValidationError
from tests.test_regresion_paginas import aplicacion, db
from tests.test_validacion_recepcion import formulario


def cliente(app, usuario=2):
    client = app.test_client()
    with client.session_transaction() as sesion:
        sesion.update(usuario_id=usuario, version_sesion=0)
    pagina = client.get("/recepcion/clientes/nuevo").get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', pagina).group(1)
    return client, token


def test_registro_completo_cotizacion_y_fragilidad(aplicacion, db):
    client, token = cliente(aplicacion)
    datos = formulario()
    datos["csrf_token"] = token
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        respuesta = client.post("/recepcion/nuevo-envio", data=datos)
    assert respuesta.status_code == 302 and "/cobrar/" in respuesta.location
    with db.cursor() as cur:
        cur.execute("SELECT es_fragil FROM bultos ORDER BY id_bulto")
        assert [bool(b["es_fragil"]) for b in cur.fetchall()] == [False, True, False]
    pagina = client.get(respuesta.location)
    assert pagina.status_code == 200


@pytest.mark.parametrize("campo,valor", [("dest_nombre", "123456"), ("direccion_destino", "a" * 201), ("valor_declarado", "NaN"), ("id_localidad_destino", "999999"), ("modalidad_pago", "inventada")])
def test_rechazo_no_crea_clientes_ni_envio(aplicacion, db, campo, valor):
    client, token = cliente(aplicacion)
    datos = formulario()
    datos[campo] = valor
    datos["csrf_token"] = token
    respuesta = client.post("/recepcion/nuevo-envio", data=datos)
    assert respuesta.status_code == 400
    assert "Juan" in respuesta.get_data(as_text=True)
    with db.cursor() as cur:
        for tabla in ("clientes", "envios", "bultos"):
            cur.execute("SELECT COUNT(*) AS total FROM " + tabla)
            assert cur.fetchone()["total"] == 0


@pytest.mark.parametrize("datos", [None, [], {"bultos": [{}], "id_localidad": 1}, {"bultos": [{"peso_real": "NaN"}], "id_localidad": 1}])
def test_api_cotizador_rechaza_400(aplicacion, datos):
    client, token = cliente(aplicacion)
    respuesta = client.post("/recepcion/cotizador/calcular", json=datos, headers={"X-CSRFToken": token})
    assert respuesta.status_code == 400
    assert respuesta.is_json and respuesta.json["error"]


def test_error_sql_controlado_html_y_json(aplicacion):
    client, token = cliente(aplicacion)
    with patch("web.routes.recepcion.ClienteController.listar_clientes", side_effect=DatabaseQueryError("SQL SELECT secreto unknown column")):
        respuesta = client.get("/recepcion/clientes")
        assert respuesta.status_code == 503 and b"SQL SELECT" not in respuesta.data
        assert len(respuesta.data) > 300
    with patch("web.routes.recepcion.EnvioController.cotizar_envio", side_effect=DatabaseQueryError("SQL SELECT secreto")):
        respuesta = client.post("/recepcion/cotizador/calcular", json={"bultos": [], "id_localidad": 1}, headers={"X-CSRFToken": token})
        assert respuesta.status_code == 503 and respuesta.is_json
        assert b"SQL SELECT" not in respuesta.data


def test_aperturas_concurrentes_no_duplican_caja(db):
    barrera = Barrier(2)
    def abrir(_):
        barrera.wait(timeout=10)
        try:
            CajaController(db).abrir_turno(2, 100)
            return True
        except TurnoCajaError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(abrir, range(2))) == [False, True]


def test_cierre_ajeno_rechazado_y_doble_cierre(db):
    caja = CajaController(db)
    turno = caja.abrir_turno(2, 100)
    with pytest.raises(TurnoCajaError):
        caja.cerrar_turno(turno.id_turno, 1)
    assert caja.cerrar_turno(turno.id_turno, 2)["total_caja_fisica"] == 100
    with pytest.raises(TurnoCajaError):
        caja.cerrar_turno(turno.id_turno, 2)


@pytest.mark.parametrize("monto", ["NaN", -1, "10000000000", "1.001"])
def test_apertura_invalida_sin_escritura(db, monto):
    with pytest.raises(ValidationError):
        CajaController(db).abrir_turno(2, monto)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM turnos_caja")
        assert cur.fetchone()["total"] == 0


def envio(db):
    clientes = ClienteController(db)
    remitente = clientes.registrar_cliente("12345678", "Juan Pérez", "3704123456")
    destino = clientes.registrar_cliente("23456789", "María Gómez", "3704654321")
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        return EnvioController(db).crear_envio(remitente.id_cliente, destino.id_cliente, 1,
            "San Martín 123", [{"peso_real": 10, "peso_volumetrico": 0}])


def test_cobro_exacto_vuelto_y_cierre_concilian(db):
    registro = envio(db)
    caja = CajaController(db)
    turno = caja.abrir_turno(2, 100)
    monto = registro["cotizacion"]["costo_total"]
    pago = EnvioController(db).registrar_pago(registro["id_envio"], monto,
        id_turno=turno.id_turno, id_usuario=2, monto_entregado=monto + 50)
    assert pago["vuelto"] == 50
    resumen = caja.cerrar_turno(turno.id_turno, 2)
    assert resumen["total_caja_fisica"] == monto + 100
    assert resumen["cantidad_operaciones"] == 1
    with pytest.raises(ValidationError):
        EnvioController(db).registrar_pago(registro["id_envio"], monto,
            id_turno=turno.id_turno, id_usuario=2, monto_entregado=monto)


def test_importe_alterado_y_turno_ajeno_no_registran_pago(db):
    registro = envio(db)
    turno = CajaController(db).abrir_turno(2, 0)
    monto = registro["cotizacion"]["costo_total"]
    for actor, importe in [(2, monto + 1), (1, monto)]:
        with pytest.raises(ValidationError):
            EnvioController(db).registrar_pago(registro["id_envio"], importe,
                id_turno=turno.id_turno, id_usuario=actor, monto_entregado=importe)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM pagos")
        assert cur.fetchone()["total"] == 0


def test_pago_concurrente_con_cierre_no_queda_fuera_de_conciliacion(db):
    registro = envio(db)
    turno = CajaController(db).abrir_turno(2, 0)
    monto = registro["cotizacion"]["costo_total"]
    barrera = Barrier(2)
    def cobrar():
        barrera.wait(timeout=10)
        try:
            EnvioController(db).registrar_pago(registro["id_envio"], monto,
                id_turno=turno.id_turno, id_usuario=2, monto_entregado=monto)
            return True
        except ValidationError:
            return False
    def cerrar():
        barrera.wait(timeout=10)
        return CajaController(db).cerrar_turno(turno.id_turno, 2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pago, cierre = pool.submit(cobrar), pool.submit(cerrar)
        cobrado, resumen = pago.result(timeout=15), cierre.result(timeout=15)
    assert resumen["ingresos_efectivo"] == (monto if cobrado else 0)


def test_fallo_al_cerrar_revierte_estado(db):
    caja = CajaController(db)
    turno = caja.abrir_turno(2, 0)
    with db.cursor(False) as cur:
        cur.execute("CREATE TRIGGER fallo_caja BEFORE UPDATE ON turnos_caja FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
    with pytest.raises(DatabaseQueryError):
        caja.cerrar_turno(turno.id_turno, 2)
    with db.cursor() as cur:
        cur.execute("SELECT estado_caja,fecha_cierre FROM turnos_caja WHERE id_turno=%s", (turno.id_turno,))
        assert cur.fetchone() == {"estado_caja": "abierto", "fecha_cierre": None}


def test_recorrido_http_caja_cobro_y_comprobante(aplicacion, db):
    registro = envio(db)
    monto = registro["cotizacion"]["costo_total"]
    client, token = cliente(aplicacion)
    assert client.post("/recepcion/caja/abrir", data={"saldo_inicial": "100", "csrf_token": token}).status_code == 302
    assert client.get("/recepcion/caja").status_code == 200
    ruta = "/recepcion/cobrar/" + registro["nro_guia"]
    datos = dict(monto=str(monto), monto_entregado="NaN", tipo_pago="efectivo", csrf_token=token)
    assert client.post(ruta, data=datos).status_code == 400
    datos["monto_entregado"] = str(monto + 50)
    respuesta = client.post(ruta, data=datos)
    assert respuesta.status_code == 302 and "/comprobante/" in respuesta.location
    assert client.get(respuesta.location).status_code == 200
    assert client.get("/recepcion/caja").status_code == 200
    with db.cursor() as cur:
        cur.execute("SELECT id_turno FROM turnos_caja WHERE id_recepcionista=2")
        turno = cur.fetchone()["id_turno"]
    assert client.post(f"/recepcion/caja/cerrar/{turno}", data={"csrf_token": token}).status_code == 302
    assert client.get("/recepcion/caja").status_code == 200
