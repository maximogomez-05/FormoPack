"""Validaciones de frontera: entradas hostiles, límites y formatos reales."""

from unittest.mock import MagicMock

import pytest
from werkzeug.datastructures import MultiDict

from app.models.cliente import Cliente
from app.models.bulto import Bulto
from app.models.solicitud_recepcion import SolicitudRecepcion
from app.controllers.cliente_controller import ClienteController
from app.controllers.envio_controller import EnvioController
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import ValidationError


@pytest.mark.parametrize("nombre", ["123456", "---", "...", "Juan1 Pérez", "Juan\nPérez", "a" * 101, None, 123, "<script>"])
def test_nombres_invalidos(nombre):
    with pytest.raises(ValidationError):
        Cliente.validar_datos("12345678", nombre, "3704123456")


@pytest.mark.parametrize("nombre", ["José Pérez", "María-José O'Connor", "João Müller", "D’Angelo", "Jose\u0301 Pérez", "Empresa S.A."])
def test_nombres_validos(nombre):
    Cliente.validar_datos("12345678", nombre, "+54 (370) 412-3456")


@pytest.mark.parametrize("campo,valor", [
    ("dni", "١٢٣٤٥٦٧٨"), ("dni", "123"), ("dni", "1234567890123456"),
    ("telefono", "1+234567"), ("telefono", "3704ABC"), ("telefono", "(" * 20 + "123456"),
    ("telefono", "123456)"), ("telefono", "1234567890123456"),
    ("email", "a b@example.com"), ("email", "a@-example.com"),
    ("email", ".a@example.com"), ("email", "a..b@example.com"),
    ("email", "a" * 90 + "@example.com"), ("email", 42),
])
def test_contactos_invalidos(campo, valor):
    datos = dict(dni="12345678", nombre_completo="Juan Pérez", telefono="3704123456", email="juan@example.com")
    datos[campo] = valor
    with pytest.raises(ValidationError):
        Cliente.validar_datos(**datos)


@pytest.mark.parametrize("valor", ["NaN", "Infinity", "-Infinity", float("nan"), -1, True, {}, "abc", "1.001", "1e1000"])
def test_numeros_invalidos(valor):
    with pytest.raises(ValidationError):
        V.decimal(valor, "importe")


@pytest.mark.parametrize("valor", [0, -1, "NaN", "999999.999", "1000000", True])
def test_peso_real_invalido(valor):
    with pytest.raises(ValidationError):
        Bulto(0, 0, valor, 0)


def test_limites_representables_y_sin_redondeo_silencioso():
    assert V.decimal("9999999999.99", "importe") == 9999999999.99
    assert Bulto(0, 0, "0.01", "0").calcular_aforo() == 0.01
    with pytest.raises(ValidationError):
        V.decimal("10000000000", "importe")


@pytest.mark.parametrize("bultos", [None, {}, [], [{}], [None], [{"peso_real": 2, "es_fragil": "false"}], [{"peso_real": 1}] * 101])
def test_bultos_malformados_no_consultan_base(bultos):
    db = MagicMock()
    with pytest.raises(ValidationError):
        EnvioController(db).cotizar_envio(bultos, 1)
    db.get_connection.assert_not_called()


def test_cliente_existente_no_evade_validacion():
    db = MagicMock()
    with pytest.raises(ValidationError):
        ClienteController(db).obtener_o_crear("12345678", "123456", "3704123456")
    db.get_connection.assert_not_called()


def formulario():
    datos = MultiDict(dict(rem_dni="12345678", rem_nombre="Juan Pérez", rem_telefono="3704123456",
        dest_dni="23456789", dest_nombre="María Gómez", dest_telefono="3704654321",
        destino_latitud="-26.1848", destino_longitud="-58.1731",
        id_localidad_destino="1", direccion_destino="Av. San Martín 123", modalidad_pago="efectivo", valor_declarado="0"))
    datos.setlist("peso_real[]", ["2", "3", "4"])
    datos.setlist("peso_volumetrico[]", ["0", "0", "0"])
    datos.setlist("es_fragil[]", ["1"])
    return datos


def test_fragilidad_del_segundo_bulto_y_listas_desparejas():
    datos = formulario()
    assert [b["es_fragil"] for b in SolicitudRecepcion(datos).bultos] == [False, True, False]
    datos.setlist("peso_volumetrico[]", ["0"])
    with pytest.raises(ValidationError):
        SolicitudRecepcion(datos)


def test_solicitud_recepcion_acepta_pin_ventana_y_prioridad_validos():
    datos = formulario()
    for campo, valor in {"destino_latitud": "-26.1834567", "destino_longitud": "-58.1734567",
        "ventana_desde": "09:00", "ventana_hasta": "12:30", "prioridad": "urgente"}.items():
        datos.setlist(campo, [valor])

    solicitud = SolicitudRecepcion(datos)

    assert solicitud.destino_latitud == -26.1834567
    assert solicitud.destino_longitud == -58.1734567
    assert solicitud.ventana_desde == "09:00:00"
    assert solicitud.ventana_hasta == "12:30:00"
    assert solicitud.prioridad == "urgente"


def test_solicitud_recepcion_rechaza_direccion_libre_sin_pin():
    datos = formulario()
    datos.setlist("destino_latitud", [""])
    datos.setlist("destino_longitud", [""])

    with pytest.raises(ValidationError, match="Seleccioná una dirección sugerida"):
        SolicitudRecepcion(datos)


@pytest.mark.parametrize("datos_nuevos", [
    {"destino_latitud": "-26.1", "destino_longitud": ""},
    {"destino_latitud": "91", "destino_longitud": "-58"},
    {"ventana_desde": "15:00", "ventana_hasta": "09:00"},
    {"ventana_desde": "09:00"},
    {"prioridad": "critica"},
])
def test_solicitud_recepcion_rechaza_datos_de_planificacion_invalidos(datos_nuevos):
    datos = formulario()
    for campo, valor in datos_nuevos.items():
        datos.setlist(campo, [valor])

    with pytest.raises(ValidationError):
        SolicitudRecepcion(datos)
