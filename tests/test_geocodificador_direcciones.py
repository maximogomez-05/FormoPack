from time import time
from unittest.mock import patch

import pytest

from app.services.geocodificador_direcciones import GeocodificadorDirecciones
from app.services.geografia_destino import centro_localidad, punto_en_localidad
from app.utils.exceptions import ValidationError
from tests.test_regresion_paginas import aplicacion, db


def test_geofence_acepta_formosa_y_rechaza_otro_pais():
    assert punto_en_localidad("Formosa Capital", -26.18, -58.17)
    assert not punto_en_localidad("Formosa Capital", 40.7128, -74.0060)


def test_geofence_no_admite_localidad_sin_centro_configurado():
    assert centro_localidad("Localidad desconocida") is None
    assert not punto_en_localidad("Localidad desconocida", -26.18, -58.17)


def test_filtrar_photon_descarta_otras_ciudades_y_puntos_fuera_del_radio():
    features = [
        {"geometry": {"coordinates": [-58.17, -26.18]}, "properties": {
            "country": "Argentina", "city": "Formosa", "street": "Avenida 25 de Mayo", "housenumber": "123"}},
        {"geometry": {"coordinates": [-57.7185, -25.2848]}, "properties": {
            "country": "Argentina", "city": "Clorinda", "street": "Calle 1"}},
        {"geometry": {"coordinates": [-74.0060, 40.7128]}, "properties": {
            "country": "United States", "city": "New York", "street": "Broadway"}},
    ]

    sugerencias = GeocodificadorDirecciones._filtrar(features, "Formosa Capital")

    assert sugerencias == [{"direccion": "Avenida 25 de Mayo 123", "latitud": -26.18, "longitud": -58.17}]


def test_endpoint_sugerencias_filtra_con_localidad_seleccionada(aplicacion):
    app = aplicacion
    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=2, rol="recepcionista", version_sesion=0,
            inicio_sesion=time(), ultima_actividad=time())

    with patch("web.routes.recepcion._obtener_nombre_localidad", return_value="Clorinda"), \
         patch.object(GeocodificadorDirecciones, "sugerir", return_value=[{"direccion": "Calle 1", "latitud": -25.28, "longitud": -57.71}]) as sugerir:
        respuesta = cliente.get("/recepcion/direcciones/sugerencias?q=Calle+1&id_localidad=2")

    assert respuesta.status_code == 200
    assert respuesta.json["sugerencias"][0]["direccion"] == "Calle 1"
    assert respuesta.json["sugerencias"][0]["verificacion"]
    sugerir.assert_called_once_with("Calle 1", "Clorinda")


def test_endpoint_reverse_rechaza_punto_de_otra_ciudad(aplicacion):
    app = aplicacion
    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=2, rol="recepcionista", version_sesion=0,
            inicio_sesion=time(), ultima_actividad=time())

    with patch("web.routes.recepcion._obtener_nombre_localidad", return_value="Clorinda"), \
         patch.object(GeocodificadorDirecciones, "inversa") as inversa:
        respuesta = cliente.get("/recepcion/direcciones/reversa?id_localidad=2&lat=40.7128&lng=-74.006")

    assert respuesta.status_code == 400
    inversa.assert_not_called()


def test_endpoint_reverse_firma_las_coordenadas_exactas_del_click(aplicacion):
    app = aplicacion
    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=2, rol="recepcionista", version_sesion=0,
            inicio_sesion=time(), ultima_actividad=time())
    latitud, longitud = -25.2848, -57.7185
    respuesta_geocodificador = {"direccion": "Calle 1 123", "latitud": latitud + 0.00002,
        "longitud": longitud + 0.00002}

    with patch("web.routes.recepcion._obtener_nombre_localidad", return_value="Clorinda"), \
         patch.object(GeocodificadorDirecciones, "inversa", return_value=respuesta_geocodificador):
        respuesta = cliente.get(f"/recepcion/direcciones/reversa?id_localidad=2&lat={latitud}&lng={longitud}")

    sugerencia = respuesta.json["sugerencia"]
    assert respuesta.status_code == 200
    assert sugerencia["latitud"] == latitud
    assert sugerencia["longitud"] == longitud
    GeocodificadorDirecciones.validar_sugerencia(sugerencia["verificacion"], sugerencia["direccion"], 2,
        latitud, longitud)


def test_formulario_recibe_centros_y_urls_del_geocodificador(aplicacion):
    from time import time

    app = aplicacion
    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update(usuario_id=2, rol="recepcionista", version_sesion=0,
            inicio_sesion=time(), ultima_actividad=time())
    localidades = [{"id_localidad": 1, "nombre": "Formosa Capital", "distancia_km": 0}]

    with patch("web.routes.recepcion._obtener_localidades", return_value=localidades), \
         patch("web.routes.recepcion._obtener_seguros", return_value=[]):
        respuesta = cliente.get("/recepcion/nuevo-envio")

    html = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "/recepcion/direcciones/sugerencias" in html
    assert "/recepcion/direcciones/reversa" in html
    assert "-26.1848" in html


def test_token_geocodificado_rechaza_cambios_de_direccion_localidad_o_pin():
    sugerencia = {"direccion": "Avenida 25 de Mayo 123", "latitud": -26.18, "longitud": -58.17}
    token = GeocodificadorDirecciones.firmar_sugerencia(sugerencia, 1)

    GeocodificadorDirecciones.validar_sugerencia(token, sugerencia["direccion"], 1, -26.18, -58.17)
    with pytest.raises(ValidationError):
        GeocodificadorDirecciones.validar_sugerencia(token, "Calle Banana", 1, -26.18, -58.17)
    with pytest.raises(ValidationError):
        GeocodificadorDirecciones.validar_sugerencia(token, sugerencia["direccion"], 2, -26.18, -58.17)
    with pytest.raises(ValidationError):
        GeocodificadorDirecciones.validar_sugerencia(token, sugerencia["direccion"], 1, -25.28, -57.71)
