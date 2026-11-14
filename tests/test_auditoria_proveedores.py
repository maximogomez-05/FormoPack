"""Entradas hostiles y respuestas externas dañadas, sin red ni pagos reales."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.geocodificador_direcciones import GeocodificadorDirecciones as Geo, ErrorGeocodificacion
from app.services.optimizador_rutas import OptimizadorRutas
from app.utils.exceptions import ValidationError


@pytest.mark.parametrize("valor", [None, {}, "inválido", 12])
def test_photon_rechaza_coleccion_invalida(valor):
    with pytest.raises(ErrorGeocodificacion):
        Geo._filtrar(valor, "Formosa Capital")


@pytest.mark.parametrize("feature", [None, [], 42, {"geometry": "incorrecta"},
    {"properties": "incorrectas"}, {"geometry": {"coordinates": 42}},
    {"geometry": {"coordinates": [True, False]}},
    {"geometry": {"coordinates": [float("nan"), float("inf")]}}])
def test_photon_descarta_elementos_invalidos_sin_caer(feature):
    valido = {"geometry": {"coordinates": [-58.17, -26.18]},
        "properties": {"country": "Argentina", "street": "Calle de prueba"}}
    assert len(Geo._filtrar([feature, valido], "Formosa Capital")) == 1


@pytest.mark.parametrize("lat,lng", [(float("nan"), -58.17), (-26.18, float("nan")),
    (float("inf"), -58.17), (91, -58.17), (-26.18, 181)])
def test_token_no_acepta_coordenadas_no_finitas_o_fuera_de_rango(lat, lng):
    token = Geo.firmar_sugerencia({"direccion": "Calle 123", "latitud": -26.18, "longitud": -58.17}, 1)
    with pytest.raises(ValidationError):
        Geo.validar_sugerencia(token, "Calle 123", 1, lat, lng)


@pytest.mark.parametrize("matriz", [None, [], [[0]], [[0, 1]], [[0, 1], [1]],
    [[0, -1], [1, 0]], [[0, True], [1, 0]], [[0, "1"], [1, 0]],
    [[0, float("nan")], [1, 0]], [[0, float("inf")], [1, 0]],
    [[0, 1e100], [1, 0]]])
@pytest.mark.parametrize("campo", ["durations", "distances"])
def test_osrm_danado_usa_distancias_aproximadas(matriz, campo, monkeypatch):
    monkeypatch.setenv("FORMOPACK_OSRM_URL", "https://osrm.invalid")
    datos = {"code": "Ok", "durations": [[0, 60], [60, 0]], "distances": [[0, 500], [500, 0]]}
    datos[campo] = matriz
    respuesta = MagicMock()
    respuesta.__enter__.return_value.read.return_value = json.dumps(datos).encode()
    with patch("app.services.optimizador_rutas.urlopen", return_value=respuesta):
        tiempos, distancias, fuente = OptimizadorRutas._matrices([(-26.18, -58.17), (-26.19, -58.18)])
    assert fuente == "geográfica aproximada"
    assert len(tiempos) == len(distancias) == 2
    assert tiempos[0][1] > 0 and distancias[0][1] > 0


def test_osrm_valido_conserva_datos_viales(monkeypatch):
    monkeypatch.setenv("FORMOPACK_OSRM_URL", "https://osrm.invalid")
    respuesta = MagicMock()
    respuesta.__enter__.return_value.read.return_value = json.dumps({"code": "Ok",
        "durations": [[0, 90], [120, 0]], "distances": [[0, 500], [800, 0]]}).encode()
    with patch("app.services.optimizador_rutas.urlopen", return_value=respuesta):
        tiempos, distancias, fuente = OptimizadorRutas._matrices([(-26.18, -58.17), (-26.19, -58.18)])
    assert (tiempos, distancias, fuente) == ([[0, 2], [2, 0]], [[0, 500], [800, 0]], "OSRM privado")
