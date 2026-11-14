"""Las pruebas nunca deben enviar correo ni operar servicios financieros reales."""

import smtplib
import sys
from urllib.parse import urlsplit

import pytest
import requests
import urllib.request


@pytest.fixture(autouse=True)
def servicios_externos_aislados(monkeypatch):
    def correo_bloqueado(*args, **kwargs):
        raise RuntimeError("SMTP real bloqueado durante pruebas; usá un proveedor simulado")

    def comprobar_local(url):
        if urlsplit(str(url)).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Red externa bloqueada durante pruebas; simulá la respuesta del proveedor")

    request_original = requests.sessions.Session.request
    abrir_original = urllib.request.urlopen

    def solicitud_local(self, method, url, *args, **kwargs):
        comprobar_local(url)
        return request_original(self, method, url, *args, **kwargs)

    def abrir_local(url, *args, **kwargs):
        comprobar_local(getattr(url, "full_url", url))
        return abrir_original(url, *args, **kwargs)

    monkeypatch.setattr(smtplib, "SMTP", correo_bloqueado)
    monkeypatch.setattr(smtplib, "SMTP_SSL", correo_bloqueado)
    monkeypatch.setattr(requests.sessions.Session, "request", solicitud_local)
    monkeypatch.setattr(urllib.request, "urlopen", abrir_local)
    # También cubrir los alias importados antes de comenzar cada prueba.
    for nombre, modulo in tuple(sys.modules.items()):
        if nombre.startswith('app.') and getattr(modulo, 'urlopen', None) is abrir_original:
            monkeypatch.setattr(modulo, 'urlopen', abrir_local)
