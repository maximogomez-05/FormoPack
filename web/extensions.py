"""Extensiones de Flask inicializables centralizadamente."""

import os
from ipaddress import ip_address
from flask import request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()


def direccion_cliente():
    origen = get_remote_address()
    if os.getenv("FORMOPACK_PROXY_LOCAL") == "1" and request.remote_addr in {"127.0.0.1", "::1"}:
        try:
            return str(ip_address(request.headers.get("X-Real-IP", "")))
        except ValueError:
            pass
    return origen


limiter = Limiter(
    key_func=direccion_cliente,
    default_limits=[],
    storage_uri="memory://",
)
