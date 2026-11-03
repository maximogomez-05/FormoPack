"""Vencimientos y revocación entre navegadores sobre persistencia aislada."""

from time import time

import pytest

from tests.test_regresion_paginas import aplicacion, db


def ingresar(app):
    cliente = app.test_client()
    app.config["WTF_CSRF_ENABLED"] = False
    respuesta = cliente.post("/login", data={"email": "admin@formopack.com", "password": "admin123"})
    assert respuesta.status_code == 302
    return cliente


def estado(cliente):
    return cliente.get("/sesion", headers={"Accept": "application/json"})


def test_nuevo_login_revoca_anterior_y_logout_revoca_cookie(aplicacion):
    primero = ingresar(aplicacion)
    segundo = ingresar(aplicacion)
    assert estado(primero).status_code == 401
    assert estado(segundo).status_code == 200
    cookie = segundo.get_cookie("session").value
    assert segundo.get("/logout").status_code == 302
    copia = aplicacion.test_client()
    copia.set_cookie("session", cookie)
    assert estado(copia).status_code == 401


@pytest.mark.parametrize("tipo", ["inactividad", "absoluto", "legacy"])
def test_vencida_no_admite_lecturas_ni_escrituras(aplicacion, tipo):
    cliente = ingresar(aplicacion)
    with cliente.session_transaction() as sesion:
        if tipo == "inactividad":
            sesion["ultima_actividad"] = time() - 1801
        elif tipo == "absoluto":
            sesion["inicio_sesion"] = time() - 12 * 3600
        else:
            sesion.pop("inicio_sesion")
    respuesta = cliente.post("/admin/envios/1/actualizar-estado",
                             json={"nuevo_estado": "en_planta"})
    assert respuesta.status_code == 401
    assert estado(cliente).status_code == 401


def test_sondeos_no_renuevan_actividad(aplicacion):
    cliente = ingresar(aplicacion)
    with cliente.session_transaction() as sesion:
        actividad = time() - 100
        sesion["ultima_actividad"] = actividad
    assert estado(cliente).status_code == 200
    cliente.get("/admin/logistica/mapa/envios")
    with cliente.session_transaction() as sesion:
        assert sesion["ultima_actividad"] == actividad
    cliente.get("/admin/dashboard")
    with cliente.session_transaction() as sesion:
        assert sesion["ultima_actividad"] > actividad
