"""Outbox: transacción real, concurrencia y SMTP simulado, sin correo externo."""
import json
import smtplib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

import pytest

from app.services.cola_notificaciones import ColaNotificaciones, TransporteSMTP
from app.services.operaciones_logisticas import OperacionesLogisticas
from app.services.servicio_notificacion import ServicioNotificacion
from app.controllers.envio_controller import EnvioController
from config.settings import EmailConfig
from tests.test_regresion_paginas import db
from tests.test_seguridad_bd import ROOT
from tests.test_recepcion_bd import envio


def encolar(db, evento="prueba:1", correo="cliente@example.com"):
    with db.cursor() as cur:
        return ColaNotificaciones.encolar(cur, evento, correo, "FormoPack", "Aviso de prueba")


def filas(db):
    with db.cursor() as cur:
        cur.execute("SELECT * FROM notificaciones_operativas ORDER BY id_notificacion")
        return cur.fetchall()


def vencer(db):
    with db.cursor() as cur:
        cur.execute("UPDATE notificaciones_operativas SET disponible_en=NOW()-INTERVAL 1 SECOND,bloqueo_hasta=NOW()-INTERVAL 1 SECOND")


def test_encolado_idempotente_por_evento_y_destinatario(db):
    encolar(db)
    encolar(db, correo="CLIENTE@example.com")
    encolar(db, evento="prueba:2")
    encolar(db, correo="otra@example.com")
    assert len(filas(db)) == 3


def test_alta_encola_sin_depender_del_helper_posterior_y_error_revierte_alta(db):
    registro = envio(db)
    with db.cursor() as cur:
        cur.execute("UPDATE clientes SET email=CONCAT('cliente',id_cliente,'@example.com')")
        cur.execute("SELECT id_remitente,id_destinatario FROM envios WHERE id_envio=%s", (registro["id_envio"],))
        personas = cur.fetchone()
    ctrl = EnvioController(db)
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        ctrl.crear_envio(personas["id_remitente"], personas["id_destinatario"], 1, "Calle Prueba 123",
                         [{"peso_real": 1, "peso_volumetrico": 0}])
    assert len(filas(db)) == 2
    assert all("recibido" in json.loads(f["contenido"])["asunto"] for f in filas(db))
    with patch.object(ColaNotificaciones, "encolar_historial", side_effect=RuntimeError("fallo de cola")):
        with pytest.raises(Exception):
            ctrl.crear_envio(personas["id_remitente"], personas["id_destinatario"], 1, "Calle Prueba 124",
                             [{"peso_real": 1, "peso_volumetrico": 0}])
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM envios")
        assert cur.fetchone()["total"] == 2
    assert len(filas(db)) == 2


@pytest.mark.parametrize("correo", [None, "", "invalido", "a@example.com\r\nBcc: otra@example.com"])
def test_destinatarios_invalidos_no_crean_trabajo(db, correo):
    assert not encolar(db, correo=correo)
    assert filas(db) == []


def test_recepcion_y_cambio_encolan_en_la_transaccion_y_congelan_estado(db):
    registro = envio(db)
    with db.cursor() as cur:
        cur.execute("UPDATE clientes SET email='comun@example.com'")
    with patch("app.services.operaciones_logisticas.notificar_cambio_estado_async"):
        OperacionesLogisticas(db).actualizar_manual(registro["id_envio"], "en_planta", 2, "Central", "Ingreso de prueba")
    datos = filas(db)
    assert len(datos) == 1  # Ambos roles con el mismo correo.
    assert "en planta" in json.loads(datos[0]["contenido"])["asunto"]
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        OperacionesLogisticas._historial(cur, registro["id_envio"], "en_ruta", 2, "Ruta", "No confirmar")
        conn.rollback()
    finally:
        cur.close()
        conn.close()
    assert len(filas(db)) == 1


def test_error_encolado_revierte_cambio_logistico(db):
    registro = envio(db)
    with patch.object(ColaNotificaciones, "encolar_historial", side_effect=RuntimeError("fallo de escritura")):
        with pytest.raises(Exception):
            OperacionesLogisticas(db).actualizar_manual(registro["id_envio"], "en_planta", 2, "Central", "Ingreso de prueba")
    with db.cursor() as cur:
        cur.execute("SELECT estado_actual FROM envios WHERE id_envio=%s", (registro["id_envio"],))
        assert cur.fetchone()["estado_actual"] == "recibido"


def test_reintento_progresivo_y_exito_sin_duplicar(db, caplog):
    encolar(db)
    transporte = Mock()
    transporte.enviar.side_effect = smtplib.SMTPException("secreto@example.com TOKEN_NO_REGISTRAR")
    cola = ColaNotificaciones(db, transporte)
    assert cola.procesar() == 0
    trabajo = filas(db)[0]
    assert trabajo["estado"] == "pendiente" and trabajo["intentos"] == 1
    assert (trabajo["disponible_en"] - trabajo["creado_en"]).total_seconds() >= 59
    assert "TOKEN_NO_REGISTRAR" not in caplog.text + trabajo["ultimo_error"]
    cola.procesar()
    assert transporte.enviar.call_count == 1  # No adelantar el reintento.
    vencer(db)
    transporte.enviar.side_effect = None
    assert cola.procesar() == 1
    assert ColaNotificaciones(db, transporte).procesar() == 0
    assert filas(db)[0]["estado"] == "enviado"


def test_intentos_agotados_no_se_reclaman_y_rechazo_destinatario_es_definitivo(db):
    encolar(db)
    transporte = Mock()
    transporte.enviar.side_effect = TimeoutError()
    cola = ColaNotificaciones(db, transporte)
    for _ in range(5):
        vencer(db)
        cola.procesar()
    assert filas(db)[0]["estado"] == "fallido"
    assert cola.reclamar() is None
    encolar(db, evento="prueba:2")
    transporte.enviar.side_effect = smtplib.SMTPRecipientsRefused({"cliente@example.com": (550, b"rechazo")})
    cola.procesar()
    assert filas(db)[1]["estado"] == "fallido"


def test_rechazo_smtp_temporal_se_reintenta(db):
    encolar(db)
    transporte = Mock()
    transporte.enviar.side_effect = smtplib.SMTPRecipientsRefused({"cliente@example.com": (450, b"temporal")})
    ColaNotificaciones(db, transporte).procesar()
    assert filas(db)[0]["estado"] == "pendiente"


def test_dos_procesadores_concurrentes_no_comparten_trabajo(db):
    encolar(db)
    barrera = Barrier(2)
    def reclamar(_):
        barrera.wait(timeout=5)
        return ColaNotificaciones(db).reclamar()
    with ThreadPoolExecutor(max_workers=2) as pool:
        trabajos = list(pool.map(reclamar, range(2)))
    assert len([t for t in trabajos if t]) == 1
    assert filas(db)[0]["intentos"] == 1


def test_lease_recupera_caida_y_cambia_token(db):
    encolar(db)
    cola = ColaNotificaciones(db)
    anterior = cola.reclamar()
    assert cola.reclamar() is None
    vencer(db)
    nuevo = cola.reclamar()
    assert nuevo["id_notificacion"] == anterior["id_notificacion"]
    assert nuevo["token"] != anterior["token"] and nuevo["intentos"] == 2
    with db.cursor() as cur:
        cur.execute("UPDATE notificaciones_operativas SET estado='enviado' WHERE token=%s", (anterior["token"],))
        assert cur.rowcount == 0


def test_caida_en_ultimo_intento_se_marca_fallido(db):
    encolar(db)
    with db.cursor() as cur:
        cur.execute("UPDATE notificaciones_operativas SET estado='procesando',intentos=5,bloqueo_hasta=NOW()-INTERVAL 1 SECOND")
    assert ColaNotificaciones(db).reclamar() is None
    assert filas(db)[0]["estado"] == "fallido"


def test_smtp_id_estable_tls_timeout_y_sin_datos_en_logs(monkeypatch):
    monkeypatch.setattr(EmailConfig, "USER", "emisor@example.com")
    monkeypatch.setattr(EmailConfig, "PASSWORD", "no_real")
    monkeypatch.setattr(EmailConfig, "PORT", 587)
    trabajo = {"contenido": json.dumps({"asunto": "Prueba", "texto": "Texto"}), "destinatario": "cliente@example.com", "clave_evento": "a"*64}
    with patch("app.services.cola_notificaciones.smtplib.SMTP") as smtp:
        smtp.return_value.send_message.return_value = {}
        TransporteSMTP().enviar(trabajo)
        assert smtp.call_args.kwargs["timeout"] == 15
        smtp.return_value.starttls.assert_called_once()
        assert smtp.return_value.send_message.call_args.args[0]["Message-ID"] == f'<{"a"*64}@formopackexpress.tech>'


def test_otp_no_se_persiste_ni_se_registra_en_logs(monkeypatch, caplog):
    monkeypatch.setattr(EmailConfig, "USER", "")
    monkeypatch.setattr(EmailConfig, "PASSWORD", "")
    ServicioNotificacion().enviar_codigo_recuperacion("privado@example.com", "Nombre", "978123")
    assert "978123" not in caplog.text and "privado@example.com" not in caplog.text


def test_alertas_manuales_encolan_sin_smtp_y_sin_duplicar(db, monkeypatch):
    from web.routes.admin import _enviar_alertas_gmail
    monkeypatch.setattr(EmailConfig, "USER", "emisor@example.com")
    monkeypatch.setattr(EmailConfig, "PASSWORD", "no_real")
    monkeypatch.setattr(EmailConfig, "RECIPIENT", "aviso@example.com,AVISO@example.com")
    with patch("web.routes.admin.DatabaseManager.get_instance", return_value=db), patch("smtplib.SMTP_SSL") as smtp:
        _enviar_alertas_gmail([{"guia": "FP-TEST", "mensaje": "Demora en reparto"}])
        _enviar_alertas_gmail([{"guia": "FP-TEST", "mensaje": "Demora en reparto"}])
        smtp.assert_not_called()
    assert len(filas(db)) == 1


def test_cli_resumen_no_envia_y_sin_credenciales_preserva_pendientes(db):
    encolar(db)
    entorno = {**os.environ, "DB_HOST": "127.0.0.1", "DB_PORT": str(db.port), "DB_NAME": db.nombre,
               "DB_USER": "root", "DB_PASSWORD": "", "PYTHON_DOTENV_DISABLED": "1",
               "SECRET_KEY": "solo-pruebas-aisladas-no-produccion", "GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}
    orden = [sys.executable, str(ROOT / 'scripts/procesar_notificaciones.py')]
    resumen = subprocess.run(orden + ['--resumen'], env=entorno, capture_output=True, text=True, timeout=20)
    assert resumen.returncode == 0, resumen.stderr
    assert "pendiente: 1" in resumen.stdout
    enviar = subprocess.run(orden, env=entorno, capture_output=True, text=True, timeout=20)
    assert enviar.returncode != 0 and "SMTP no configurado" in enviar.stderr
    assert filas(db)[0]["intentos"] == 0
