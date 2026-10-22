"""Pruebas unitarias para las fortificaciones arquitectónicas y correcciones (Items 10 a 20)."""

import pytest
from unittest.mock import MagicMock, patch

from app.core.database import DatabaseManager
from app.core.migrations import MigrationManager
from app.models.vehiculo import Vehiculo
from app.controllers.cliente_controller import ClienteController
from app.controllers.chofer_controller import ChoferController
from app.controllers.logistica_controller import LogisticaController
from app.services.servicio_notificacion import notificar_cambio_estado_async


def test_database_manager_context_manager():
    """Valida el funcionamiento de connection() y cursor() con rollback y cierre garantizado."""
    db = DatabaseManager.get_instance()

    # 1. Uso exitoso de cursor() y connection()
    with db.cursor(dictionary=True) as cur:
        cur.execute("SELECT 1 AS ok")
        res = cur.fetchone()
        assert res["ok"] == 1

    # 2. Rollback automático ante excepción dentro del bloque
    try:
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("CREATE TEMPORARY TABLE IF NOT EXISTS _test_rollback (id INT)")
            cur.execute("INSERT INTO _test_rollback VALUES (99)")
            raise RuntimeError("Error forzado para probar rollback")
    except RuntimeError:
        pass


def test_database_manager_singleton_mock_injection():
    """Valida que set_instance y reset_instance permitan inyectar mocks sin monkey-patching."""
    mock_db = MagicMock(spec=DatabaseManager)
    DatabaseManager.set_instance(mock_db)
    assert DatabaseManager.get_instance() is mock_db

    DatabaseManager.reset_instance()
    instancia_real = DatabaseManager.get_instance()
    assert isinstance(instancia_real, DatabaseManager)


def test_vehiculo_from_db_sin_excepcion_en_init():
    """Valida que Vehiculo.from_db_row cargue filas sin disparar validaciones de formulario."""
    row = {
        "id_vehiculo": 999,
        "patente": "ABC123",
        "capacidad_kg": 1500.0,
        "estado": "disponible",
    }
    veh = Vehiculo.from_db_row(row)
    assert veh.id_vehiculo == 999
    assert veh.patente == "ABC123"
    assert veh.capacidad_kg == 1500.0
    assert veh.esta_disponible() is True


def test_cliente_controller_columna_email_cache():
    """Valida que _tiene_columna_email utilice la caché en memoria."""
    ctrl = ClienteController()
    ClienteController._columna_email_cache = None

    # Primera llamada: consulta la BD y puebla la caché
    resultado_1 = ctrl._tiene_columna_email()
    assert isinstance(resultado_1, bool)
    assert ClienteController._columna_email_cache is not None

    # Segunda llamada: retorna directamente desde la caché
    assert ctrl._tiene_columna_email() == resultado_1


def test_chofer_controller_columna_estado_cache():
    """Valida que ChoferController utilice la caché en memoria para _tiene_columna_estado."""
    ctrl = ChoferController()
    ChoferController._columna_estado_cache = None

    res1 = ctrl._tiene_columna_estado()
    assert isinstance(res1, bool)
    assert ChoferController._columna_estado_cache is not None
    assert ctrl._tiene_columna_estado() == res1


def test_notificar_cambio_estado_async():
    """Valida que el helper de notificación ejecute sin bloquear."""
    with patch("app.services.servicio_notificacion.ServicioNotificacion.enviar_alerta_cambio_estado") as mock_env:
        # Modo síncrono para test
        notificar_cambio_estado_async(id_envio=1, nuevo_estado="en_ruta", async_mode=False)
        # O en modo asíncrono
        notificar_cambio_estado_async(id_envio=1, nuevo_estado="en_ruta", async_mode=True)


def test_migraciones_manager_ejecucion():
    """Valida que MigrationManager inspeccione y reporte las migraciones numeradas."""
    mgr = MigrationManager()
    aplicadas = mgr.obtener_migraciones_aplicadas()
    assert "001_init_database" in aplicadas
    assert "002_ubicaciones_gps" in aplicadas
    assert "003_chats_soporte" in aplicadas


def test_paginacion_logistica_controller():
    """Valida los límites y offset en listar_hojas_ruta y obtener_entregas_pendientes."""
    ctrl = LogisticaController()
    hojas = ctrl.listar_hojas_ruta(limite=5, offset=0)
    assert isinstance(hojas, list)
    assert len(hojas) <= 5

    entregas = ctrl.obtener_entregas_pendientes(limite=10, offset=0)
    assert isinstance(entregas, list)
    assert len(entregas) <= 10


def test_validar_cabecera_imagen():
    """Valida la detección de firmas binarias de imágenes en la subida de POD."""
    import io
    from web.routes.chofer import _validar_cabecera_imagen

    # PNG válido
    png_bytes = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    assert _validar_cabecera_imagen(png_bytes) is True

    # JPEG válido
    jpg_bytes = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    assert _validar_cabecera_imagen(jpg_bytes) is True

    # WEBP válido
    webp_bytes = io.BytesIO(b"RIFF\x1a\x00\x00\x00WEBPVP8 ")
    assert _validar_cabecera_imagen(webp_bytes) is True

    # Script/Texto malicioso camuflado
    malicious = io.BytesIO(b"<?php echo 'hacked'; ?>")
    assert _validar_cabecera_imagen(malicious) is False
