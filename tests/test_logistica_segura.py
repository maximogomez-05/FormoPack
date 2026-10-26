"""Despacho, estados, visitas y recursos en una instancia aislada de MariaDB."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import mysql.connector
import pytest

from app.controllers.envio_controller import EnvioController
from app.controllers.logistica_controller import LogisticaController
from app.controllers.chofer_controller import ChoferController
from app.models.estado_envio import EstadoEnvio
from app.services.operaciones_logisticas import OperacionesLogisticas
from app.utils.exceptions import ValidationError, DatabaseQueryError
from tests.test_regresion_paginas import aplicacion, db
from tests.test_recepcion_bd import envio, cliente


@pytest.fixture(autouse=True)
def sin_correos():
    with patch("app.services.operaciones_logisticas.notificar_cambio_estado_async"):
        yield


def preparar(db, cantidad=1):
    primero = envio(db)
    ids = [primero["id_envio"]]
    with db.cursor() as cur:
        cur.execute("SELECT id_remitente,id_destinatario FROM envios WHERE id_envio=%s", (ids[0],))
        clientes = cur.fetchone()
    with patch("app.controllers.envio_controller.notificar_cambio_estado_async"):
        for n in range(cantidad - 1):
            ids.append(EnvioController(db).crear_envio(clientes["id_remitente"], clientes["id_destinatario"], 1,
                f"Calle de prueba {n + 1}", [{"peso_real": 10, "peso_volumetrico": 0}])["id_envio"])
    movil = LogisticaController(db).registrar_vehiculo("TST001", 1000)
    return ids, movil.id_vehiculo


def otro_chofer(db):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO usuarios (nombre,email,credenciales_hash,tipo_usuario)
            SELECT 'Otro Chofer','otro-chofer@example.com',credenciales_hash,'chofer' FROM usuarios WHERE id_usuario=3""")
        return cur.lastrowid


def visita(servicio, ruta, envio_id, tipo="fallido"):
    return servicio.entregar(3, ruta, envio_id, tipo,
        dni_receptor="12345678" if tipo == "entregado" else None,
        firma_receptor="firma-de-prueba" if tipo == "entregado" else None,
        motivo_fallo="destinatario_ausente" if tipo == "fallido" else None)


def test_deposito_inicio_visita_y_cierre(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    s.actualizar_manual(ids[0], "en_planta", 2, "Depósito", "Recepción física de prueba")
    hoja = s.crear("DES-TEST-01", 3, movil, ids, 1)
    with pytest.raises(ValidationError): visita(s, hoja.id_hoja_ruta, ids[0], "entregado")
    s.iniciar(3, hoja.id_hoja_ruta)
    s.iniciar(3, hoja.id_hoja_ruta)  # No duplica el historial de inicio.
    visita(s, hoja.id_hoja_ruta, ids[0], "entregado")
    with db.cursor() as cur:
        cur.execute("SELECT estado,fecha_cierre FROM hojas_de_ruta WHERE id_hoja_ruta=%s", (hoja.id_hoja_ruta,))
        fila = cur.fetchone()
        assert fila["estado"] == "cerrada" and fila["fecha_cierre"] is not None
        cur.execute("SELECT estado FROM vehiculos WHERE id_vehiculo=%s", (movil,))
        assert cur.fetchone()["estado"] == "disponible"
        cur.execute("SELECT COUNT(*) AS total FROM historial_estados WHERE id_envio=%s AND estado='en_ruta'", (ids[0],))
        assert cur.fetchone()["total"] == 1


def test_tres_rutas_fallidas_conservan_historia_y_bloquean_cuarto_intento(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    rutas = []
    for n in range(3):
        h = s.crear(f"DES-TEST-{n}", 3, movil, ids, 1)
        rutas.append(h.id_hoja_ruta)
        s.iniciar(3, h.id_hoja_ruta)
        visita(s, h.id_hoja_ruta, ids[0])
        with pytest.raises(ValidationError): visita(s, h.id_hoja_ruta, ids[0])
    with pytest.raises(ValidationError): s.crear("DES-CUARTO", 3, movil, ids, 1)
    with pytest.raises(ValidationError): s.actualizar_manual(ids[0], "en_planta", 1, "Depósito", "Intento de reprogramación")
    for ruta in rutas:
        h = LogisticaController(db).obtener_hoja_ruta(ruta)
        assert len(h.envios) == 1 and h.envios[0]["estado_actual"] == "fallido"
    assert LogisticaController(db).obtener_entregas_pendientes() == []


def test_liquidacion_conserva_visita_fallida_tras_entrega_en_otra_ruta(db):
    from datetime import date
    from app.controllers.liquidacion_controller import LiquidacionController
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    h = s.crear('DES-FALLIDA', 3, movil, ids, 1)
    s.iniciar(3, h.id_hoja_ruta)
    visita(s, h.id_hoja_ruta, ids[0])
    h2 = s.crear('DES-ENTREGADA', 3, movil, ids, 1)
    s.iniciar(3, h2.id_hoja_ruta)
    visita(s, h2.id_hoja_ruta, ids[0], 'entregado')
    with patch('app.core.database.DatabaseManager.get_instance', return_value=db):
        resultado = LiquidacionController().generar_liquidacion(3, date(2000,1,1), date(2100,1,1))
    assert resultado.total_hojas == 2
    assert resultado.total_envios == 2  # Dos asignaciones del mismo paquete.
    assert (resultado.fallidos, resultado.entregados, resultado.pendientes) == (1, 1, 0)


def test_no_reprograma_mientras_la_ruta_anterior_tiene_pendientes(db):
    ids, movil = preparar(db, 2)
    s = OperacionesLogisticas(db)
    h = s.crear("DES-ORIGINAL", 3, movil, ids, 1)
    s.iniciar(3, h.id_hoja_ruta)
    visita(s, h.id_hoja_ruta, ids[0])
    otro = otro_chofer(db)
    nuevo_movil = LogisticaController(db).registrar_vehiculo("TST002", 1000).id_vehiculo
    with pytest.raises(ValidationError): s.crear("DES-REINTENTO", otro, nuevo_movil, [ids[0]], 1)
    visita(s, h.id_hoja_ruta, ids[1], "entregado")
    assert s.crear("DES-REINTENTO", otro, nuevo_movil, [ids[0]], 1)


def test_admin_no_inventa_entrega_ni_reabre_terminal(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    for estado in ("en_ruta", "entregado", "fallido"):
        with pytest.raises(ValidationError): s.actualizar_manual(ids[0], estado, 1, "Base", "Cambio arbitrario de prueba")
    with pytest.raises(ValidationError): s.actualizar_manual(ids[0], "siniestro", 2, "Base", "Incidencia de prueba")
    h = s.crear("DES-SINIESTRO", 3, movil, ids, 1)
    s.actualizar_manual(ids[0], "siniestro", 1, "Base", "Paquete dañado en depósito")
    with pytest.raises(ValidationError): s.actualizar_manual(ids[0], "en_planta", 1, "Base", "Reapertura inválida")
    with db.cursor() as cur:
        cur.execute("SELECT estado FROM hojas_de_ruta WHERE id_hoja_ruta=%s", (h.id_hoja_ruta,))
        assert cur.fetchone()["estado"] == "cerrada"
        cur.execute("SELECT id_usuario_actor FROM historial_estados WHERE id_envio=%s AND estado='siniestro'", (ids[0],))
        assert cur.fetchone()["id_usuario_actor"] == 1


def test_capacidad_duplicados_y_actor_rechazados_antes_de_escribir(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    with pytest.raises(ValidationError): s.crear("DES-DUP", 3, movil, [ids[0], ids[0]], 1)
    with pytest.raises(ValidationError): s.crear("DES-ROL", 3, movil, ids, 2)
    with db.cursor() as cur:
        cur.execute("UPDATE vehiculos SET capacidad_kg=1 WHERE id_vehiculo=%s", (movil,))
    with pytest.raises(ValidationError): s.crear("DES-PESO", 3, movil, ids, 1)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM hojas_de_ruta")
        assert cur.fetchone()["total"] == 0


@pytest.mark.parametrize("recurso", ["chofer", "vehiculo", "envio"])
def test_despachos_concurrentes_no_comparten_recursos(db, recurso):
    ids, movil = preparar(db, 2)
    otro = otro_chofer(db)
    otro_movil = LogisticaController(db).registrar_vehiculo("TST002", 1000).id_vehiculo
    with db.cursor() as cur:
        cur.execute("INSERT INTO usuarios (nombre,email,credenciales_hash,tipo_usuario) SELECT 'Otro Admin','otro-admin@example.com',credenciales_hash,'administrador' FROM usuarios WHERE id_usuario=1")
        admin2 = cur.lastrowid
    barrera = Barrier(2)
    def crear(n):
        barrera.wait(timeout=10)
        try:
            OperacionesLogisticas(db).crear(f"DES-C-{n}", 3 if (n == 0 or recurso == "chofer") else otro,
                movil if (n == 0 or recurso == "vehiculo") else otro_movil,
                [ids[0] if (n == 0 or recurso == "envio") else ids[1]], 1 if n == 0 else admin2)
            return True
        except ValidationError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(crear, range(2))) == [False, True]


def test_sql_unico_impide_doble_ruta_y_migracion_se_repite(db):
    from tests.test_seguridad_bd import ROOT
    ids, movil = preparar(db)
    OperacionesLogisticas(db).crear("DES-UNICO", 3, movil, ids, 1)
    db.ejecutar_archivo(ROOT / "scripts/migrations/009_logistica.sql")
    with pytest.raises(mysql.connector.IntegrityError):
        with db.cursor() as cur:
            cur.execute("INSERT INTO hojas_de_ruta (nro_despacho,id_chofer,id_vehiculo) VALUES ('DES-BYPASS',3,%s)", (movil,))


def test_migracion_rechaza_conflictos_anteriores_sin_elegir_ruta(db):
    from app.core.migrations import MigrationManager
    ids, movil = preparar(db)
    OperacionesLogisticas(db).crear('DES-PREVIA', 3, movil, ids, 1)
    with db.cursor() as cur:
        cur.execute('ALTER TABLE hojas_de_ruta DROP INDEX uk_chofer_activo, DROP INDEX uk_vehiculo_activo')
        cur.execute("INSERT INTO hojas_de_ruta (nro_despacho,id_chofer,id_vehiculo) VALUES ('DES-CONFLICTO',3,%s)", (movil,))
        cur.execute("DELETE FROM schema_migrations WHERE version='009_logistica'")
    with pytest.raises(ValueError, match='varias rutas abiertas'):
        MigrationManager(db).aplicar_migraciones(desde='009')
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM hojas_de_ruta WHERE estado='abierta'")
        assert cur.fetchone()['total'] == 2


def test_fallo_al_registrar_visita_revierte_todo(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    h = s.crear("DES-ROLLBACK", 3, movil, ids, 1)
    s.iniciar(3, h.id_hoja_ruta)
    with db.cursor(False) as cur:
        cur.execute("CREATE TRIGGER fallo_visita BEFORE INSERT ON historial_estados FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
    with pytest.raises(DatabaseQueryError): visita(s, h.id_hoja_ruta, ids[0])
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM intentos_entrega")
        assert cur.fetchone()["total"] == 0
        cur.execute("SELECT estado_actual FROM envios WHERE id_envio=%s", (ids[0],))
        assert cur.fetchone()["estado_actual"] == "en_ruta"


def test_chofer_ajeno_no_inicia_ni_resuelve(db):
    ids, movil = preparar(db)
    h = OperacionesLogisticas(db).crear("DES-PROPIO", 3, movil, ids, 1)
    otro = otro_chofer(db)
    with pytest.raises(ValidationError): OperacionesLogisticas(db).iniciar(otro, h.id_hoja_ruta)
    s = OperacionesLogisticas(db)
    s.iniciar(3, h.id_hoja_ruta)
    with pytest.raises(ValidationError):
        s.entregar(otro, h.id_hoja_ruta, ids[0], 'fallido', motivo_fallo='otro')


def test_visitas_concurrentes_y_replay_no_liberan_vehiculo_reasignado(db):
    ids, movil = preparar(db, 2)
    s = OperacionesLogisticas(db)
    h = s.crear('DES-PARALELO', 3, movil, ids, 1)
    s.iniciar(3, h.id_hoja_ruta)
    barrera = Barrier(2)
    def resolver(envio_id):
        barrera.wait(timeout=10)
        visita(OperacionesLogisticas(db), h.id_hoja_ruta, envio_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(resolver, ids))
    nueva = s.crear('DES-NUEVA', 3, movil, ids, 1)
    with pytest.raises(ValidationError): visita(s, h.id_hoja_ruta, ids[0])
    with db.cursor() as cur:
        cur.execute('SELECT estado FROM vehiculos WHERE id_vehiculo=%s', (movil,))
        assert cur.fetchone()['estado'] == 'reservado'
        cur.execute('SELECT COUNT(*) AS total FROM intentos_entrega')
        assert cur.fetchone()['total'] == 2
        cur.execute('SELECT estado FROM hojas_de_ruta WHERE id_hoja_ruta=%s', (nueva.id_hoja_ruta,))
        assert cur.fetchone()['estado'] == 'abierta'


def test_inicio_rechaza_vehiculo_en_mantenimiento(db):
    ids, movil = preparar(db)
    s = OperacionesLogisticas(db)
    h = s.crear('DES-MANT', 3, movil, ids, 1)
    with db.cursor() as cur:
        cur.execute("UPDATE vehiculos SET estado='mantenimiento' WHERE id_vehiculo=%s", (movil,))
    with pytest.raises(ValidationError): s.iniciar(3, h.id_hoja_ruta)


def test_siniestro_parcial_no_impide_iniciar_pendientes(db):
    ids, movil = preparar(db, 2)
    s = OperacionesLogisticas(db)
    h = s.crear('DES-PARCIAL', 3, movil, ids, 1)
    s.actualizar_manual(ids[0], 'siniestro', 1, 'Depósito', 'Paquete dañado antes de salir')
    s.iniciar(3, h.id_hoja_ruta)
    visita(s, h.id_hoja_ruta, ids[1], 'entregado')
    with db.cursor() as cur:
        cur.execute('SELECT estado_actual FROM envios WHERE id_envio=%s', (ids[0],))
        assert cur.fetchone()['estado_actual'] == 'siniestro'
        cur.execute('SELECT estado FROM hojas_de_ruta WHERE id_hoja_ruta=%s', (h.id_hoja_ruta,))
        assert cur.fetchone()['estado'] == 'cerrada'


def test_http_no_redirige_a_referer_externo_y_recepcionista_no_despacha(aplicacion, db):
    ids, _ = preparar(db)
    c, token = cliente(aplicacion)
    r = c.post(f"/admin/envios/{ids[0]}/actualizar-estado", data={"csrf_token": token, "nuevo_estado": "entregado"}, headers={"Referer": "https://ejemplo.com"})
    assert r.location.endswith("/admin/dashboard")
    assert c.post("/admin/logistica/hojas/nueva", data={"csrf_token": token}).status_code == 403
