"""Pruebas unitarias e integrales para el Dashboard y la Actualización de Envíos."""

import pytest
from app.core.database import DatabaseManager
from web.app import create_app
from web.routes.admin import _obtener_metricas, _obtener_historico_metricas, _obtener_ultimos_envios


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["nombre"] = "Admin Test"
            sess["rol"] = "administrador"
        yield client


def test_obtener_metricas_operativas():
    """Valida que las métricas reflejen estados operativos reales de la flota."""
    metricas = _obtener_metricas()
    assert isinstance(metricas, dict)
    assert "total_envios" in metricas
    assert "en_ruta" in metricas
    assert "fallidos" in metricas
    assert "entregados" in metricas
    assert "en_planta" in metricas
    assert "total_acumulado" in metricas

    assert metricas["en_ruta"] >= 0
    assert metricas["fallidos"] >= 0
    assert metricas["total_acumulado"] >= 0


def test_obtener_historico_siete_dias_continuos():
    """Valida que el histórico entregue siempre los 7 días consecutivos."""
    historico = _obtener_historico_metricas()
    assert isinstance(historico, list)
    assert len(historico) == 7
    for dia in historico:
        assert "dia" in dia
        assert "total_envios" in dia
        assert "entregados" in dia
        assert "fallidos" in dia
        assert "facturado" in dia


def test_obtener_envios_con_filtros_y_busqueda():
    """Valida búsqueda y filtrado de envíos (antiguos y recientes)."""
    # 1. Búsqueda por texto (guía parcial o cliente)
    todos = _obtener_ultimos_envios(filtros={"limite": "todos"})
    assert isinstance(todos, list)

    # 2. Filtrar por estado 'fallido'
    fallidos = _obtener_ultimos_envios(filtros={"estado": "fallido"})
    for f in fallidos:
        assert f["estado_actual"] == "fallido"

    # 3. Filtrar por estado 'en_ruta'
    en_ruta = _obtener_ultimos_envios(filtros={"estado": "en_ruta"})
    for er in en_ruta:
        assert er["estado_actual"] == "en_ruta"

    # 4. Búsqueda por guía específica si existen envíos
    if todos:
        primera_guia = todos[0]["nro_guia"]
        busqueda = _obtener_ultimos_envios(filtros={"q": primera_guia})
        assert len(busqueda) >= 1
        assert busqueda[0]["nro_guia"] == primera_guia


def test_actualizar_estado_envio_exitoso(client):
    """Valida la actualización del estado de un envío y el registro en historial_estados."""
    db = DatabaseManager.get_instance()

    # Seleccionar un envío de prueba existente
    with db.cursor(dictionary=True) as cur:
        cur.execute("SELECT id_envio, estado_actual FROM envios LIMIT 1")
        envio_fila = cur.fetchone()

    if not envio_fila:
        pytest.skip("No hay envíos en la base de datos para probar actualización")

    id_test = envio_fila["id_envio"]
    estado_original = envio_fila["estado_actual"]
    nuevo_estado_test = "recibido" if estado_original != "recibido" else "en_planta"

    # Actualizar estado
    res = client.post(
        f"/admin/envios/{id_test}/actualizar-estado",
        data={
            "nuevo_estado": nuevo_estado_test,
            "ubicacion": "Planta Central Prueba",
            "observacion": "Cambio de estado administrativo para prueba",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    # Verificar que el estado cambió en la base de datos
    with db.cursor(dictionary=True) as cur:
        cur.execute("SELECT estado_actual FROM envios WHERE id_envio = %s", (id_test,))
        envio_actualizado = cur.fetchone()
        assert envio_actualizado["estado_actual"] == nuevo_estado_test

        # Verificar que se insertó en historial_estados
        cur.execute(
            "SELECT * FROM historial_estados WHERE id_envio = %s ORDER BY id_historial DESC LIMIT 1",
            (id_test,),
        )
        hist = cur.fetchone()
        assert hist["estado"] == nuevo_estado_test
        assert "Cambio de estado administrativo" in hist["observacion"]

    # Restaurar al estado previo
    client.post(
        f"/admin/envios/{id_test}/actualizar-estado",
        data={
            "nuevo_estado": estado_original,
            "ubicacion": "Planta Central",
            "observacion": "Restaurado tras prueba unitaria",
        },
    )


def test_actualizar_estado_invalido_es_rechazado(client):
    """Valida que un estado inexistente sea rechazado."""
    res = client.post(
        "/admin/envios/1/actualizar-estado",
        data={"nuevo_estado": "estado_magico_invalido"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "no es válido" in res.get_data(as_text=True)


def test_dashboard_render_admin_y_recepcionista(client):
    """Valida que tanto administrador como recepcionista puedan renderizar el dashboard."""
    # 1. Admin
    res_admin = client.get("/admin/dashboard")
    assert res_admin.status_code == 200
    html_admin = res_admin.get_data(as_text=True)
    assert "Panel de Control" in html_admin
    assert "Actividad Operativa de los Últimos 7 Días" in html_admin
    assert "Actualizar Estado" in html_admin

    # 2. Recepcionista
    with client.session_transaction() as sess:
        sess["rol"] = "recepcionista"
        sess["nombre"] = "Recepcionista Test"
    res_rec = client.get("/admin/dashboard")
    assert res_rec.status_code == 200
    html_rec = res_rec.get_data(as_text=True)
    assert "Panel de Control" in html_rec

    # 3. Redirección desde /dashboard
    res_dash = client.get("/dashboard", follow_redirects=False)
    assert res_dash.status_code == 302
    assert "/admin/dashboard" in res_dash.location
