"""Entradas adversariales: deben rechazarse sin redondear ni escribir datos."""

from unittest.mock import MagicMock, patch

import pytest

from app.controllers.chofer_controller import ChoferController
from app.controllers.envio_controller import EnvioController
from app.models.solicitud_recepcion import SolicitudRecepcion
from app.models.vehiculo import Vehiculo
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import ValidationError
from tests.test_regresion_paginas import aplicacion, db
from tests.test_recepcion_bd import cliente
from tests.test_recepcion_bd import envio
from app.controllers.caja_controller import CajaController
from werkzeug.datastructures import MultiDict
from tests.test_validacion_recepcion import formulario
from tests.test_logistica_segura import preparar
from app.services.operaciones_logisticas import OperacionesLogisticas


@pytest.mark.parametrize("valor", ["1_000", "1\n", "\t1", "١٢", "１２"])
def test_numeros_no_admiten_sintaxis_ajena_al_formulario(valor):
    with pytest.raises(ValidationError):
        V.decimal(valor, "importe")


@pytest.mark.parametrize("valor", [True, None, {}, "1000.0000000000000001"])
def test_vehiculo_valida_antes_de_convertir_a_float(valor):
    with pytest.raises(ValidationError):
        Vehiculo(0, "TST001", valor)


@pytest.mark.parametrize("campo,valor", [
    ("latitud", True), ("longitud", False), ("latitud", "NaN"),
    ("precision_m", -1), ("precision_m", float("inf")),
    ("precision_m", float("nan")), ("precision_m", 1000000),
])
def test_gps_invalido_no_consulta_la_base(campo, valor):
    datos = dict(latitud=-26.18, longitud=-58.17, precision_m=5)
    datos[campo] = valor
    base = MagicMock()
    with pytest.raises(ValidationError):
        ChoferController(base).actualizar_ubicacion_ruta(3, 1, **datos)
    base.get_connection.assert_not_called()


def test_nombre_normalizado_se_persiste_sin_desbordar(db):
    datos = formulario()
    datos["rem_nombre"] = "e\u0301" * 100
    solicitud = SolicitudRecepcion(datos)
    assert solicitud.clientes["rem"]["nombre_completo"] == "é" * 100
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        EnvioController(db).registrar_en_mostrador(solicitud, 2, "c" * 32)
    with db.cursor() as cur:
        cur.execute("SELECT nombre_completo FROM clientes WHERE dni='12345678'")
        assert cur.fetchone()["nombre_completo"] == "é" * 100


@pytest.mark.parametrize("campo", ["rem_dni", "id_localidad_destino", "modalidad_pago", "solicitud_id"])
def test_formulario_ambiguo_rechazado_sin_escrituras(aplicacion, db, campo):
    navegador, csrf = cliente(aplicacion)
    datos = formulario()
    datos.update({"csrf_token": csrf, "solicitud_id": "a" * 32})
    datos.add(campo, "otro-valor")
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        respuesta = navegador.post("/recepcion/nuevo-envio", data=datos)
    assert respuesta.status_code == 400
    with db.cursor() as cur:
        for tabla in ("envios", "clientes", "solicitudes_mostrador"):
            cur.execute("SELECT COUNT(*) AS total FROM " + tabla)
            assert cur.fetchone()["total"] == 0


def test_capacidad_http_no_redondea_antes_de_validar(aplicacion, db):
    navegador, csrf = cliente(aplicacion, 1)
    navegador.post("/admin/logistica/vehiculos/nuevo", data={
        "csrf_token": csrf, "patente": "TST999", "capacidad_kg": "1000.0000000000000001"})
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM vehiculos WHERE patente='TST999'")
        assert cur.fetchone()["total"] == 0


def test_gps_http_limites_y_preservacion_del_ultimo_punto(aplicacion, db):
    navegador, csrf = cliente(aplicacion)
    with navegador.session_transaction() as sesion:
        sesion["usuario_id"] = 3
    ids, movil = preparar(db)
    with patch("app.services.operaciones_logisticas.notificar_cambio_estado_async"):
        servicio = OperacionesLogisticas(db)
        ruta = servicio.crear("GPS-PRUEBA", 3, movil, ids, 1)
        servicio.iniciar(3, ruta.id_hoja_ruta)
    url = f"/chofer/hojas/{ruta.id_hoja_ruta}/ubicacion"
    valido = dict(latitud=-26.183456789, longitud=-58.173456789, precision_m=4.123456)
    respuesta = navegador.post(url, json=valido, headers={"X-CSRFToken": csrf})
    assert respuesta.status_code == 200
    with db.cursor() as cur:
        cur.execute("SELECT latitud,longitud,precision_m FROM ubicaciones_hojas_ruta")
        original = cur.fetchone()
        assert float(original["precision_m"]) == 4.12
        assert float(original["latitud"]) == -26.1834568
    invalidos = [[], [1], True, "texto", {},
        {**valido, "latitud": True}, {**valido, "longitud": 180.00001},
        {**valido, "precision_m": -1}, {**valido, "precision_m": "Infinity"},
        {**valido, "precision_m": 1000000}]
    for datos in invalidos:
        respuesta = navegador.post(url, json=datos, headers={"X-CSRFToken": csrf})
        assert respuesta.status_code == 400, (datos, respuesta.data)
    with db.cursor() as cur:
        cur.execute("SELECT latitud,longitud,precision_m FROM ubicaciones_hojas_ruta")
        assert cur.fetchone() == original


@pytest.mark.parametrize("valor,esperado", [("1e2", 100), (" 1.20 ", 1.2), (".01", .01),
    ("9999999999.99", 9999999999.99), ("0e999999", 0)])
def test_numeros_validos_conservan_compatibilidad(valor, esperado):
    assert V.decimal(valor, "importe") == esperado


def test_cobro_repetido_en_campo_no_acredita_y_conserva_vuelto(aplicacion, db):
    registro = envio(db)
    caja = CajaController(db)
    turno = caja.abrir_turno(2, 100)
    navegador, csrf = cliente(aplicacion)
    total = registro["cotizacion"]["costo_total"]
    datos = MultiDict({"csrf_token": csrf, "tipo_pago": "efectivo",
        "monto": str(total), "monto_entregado": str(total + 500)})
    datos.add("monto", "0.01")
    respuesta = navegador.post("/recepcion/cobrar/" + registro["nro_guia"], data=datos)
    assert respuesta.status_code == 400
    assert caja.obtener_resumen(turno.id_turno)["cantidad_operaciones"] == 0
    datos.setlist("monto", [str(total)])
    assert navegador.post("/recepcion/cobrar/" + registro["nro_guia"], data=datos).status_code == 302
    resumen = caja.obtener_resumen(turno.id_turno)
    assert resumen["total_ingresos"] == total
    assert resumen["total_caja_fisica"] == total + 100


def test_matriz_json_invalida_no_escribe_ni_falla_con_500(aplicacion, db):
    navegador, csrf = cliente(aplicacion)
    original = {"id_localidad": 1, "valor_declarado": 0,
        "bultos": [{"peso_real": 1, "peso_volumetrico": 0}]}
    invalidos = [None, True, False, [], {}, "", "NaN", "Infinity", "1_000", "1,50", "\n1", "1e99999"]
    for campo in ("id_localidad", "bultos", "valor_declarado"):
        for valor in invalidos:
            datos = {**original, campo: valor}
            respuesta = navegador.post("/recepcion/cotizador/calcular", json=datos,
                headers={"X-CSRFToken": csrf})
            assert respuesta.status_code == 400, (campo, valor, respuesta.data)
            assert respuesta.is_json
    for campo in ("peso_real", "peso_volumetrico", "es_fragil"):
        for valor in [None, {}, [], "NaN", "<script>"]:
            datos = {**original, "bultos": [{**original["bultos"][0], campo: valor}]}
            respuesta = navegador.post("/recepcion/cotizador/calcular", json=datos,
                headers={"X-CSRFToken": csrf})
            assert respuesta.status_code == 400, (campo, valor, respuesta.data)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM envios")
        assert cur.fetchone()["total"] == 0
