"""Pruebas unitarias e integrales para el sistema de Soporte al Cliente y Chats."""

import uuid
import pytest
from app.controllers.soporte_controller import SoporteController
from web.app import create_app


@pytest.fixture
def app_client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app.test_client()


def test_soporte_controller_ciclo_completo():
    """Valida el flujo de atención: creación, asignación única, envío de mensajes y eliminación."""
    ctrl = SoporteController()
    session_id = f"test-session-{uuid.uuid4().hex[:10]}"

    # Limpieza previa de chats de prueba para los operadores de test
    conn_clean = ctrl._db.get_connection()
    try:
        cur_clean = conn_clean.cursor()
        cur_clean.execute("DELETE FROM chats_soporte WHERE id_usuario_atendiendo IN (1, 2) OR session_id LIKE 'test-%'")
        conn_clean.commit()
    finally:
        conn_clean.close()

    # 1. El cliente inicia un chat
    chat = ctrl.obtener_o_crear_chat(
        session_id=session_id,
        cliente_nombre="Carlos Destinatario",
        nro_guia="FPX-2026-TEST",
        cliente_email="carlos@example.com",
        mensaje_inicial="Hola, quiero coordinar la entrega.",
    )

    assert chat is not None
    assert chat["estado"] == "sin_atender"
    assert chat["cliente_nombre"] == "Carlos Destinatario"
    id_chat_1 = chat["id_chat"]

    # Verificar que el mensaje inicial se guardó
    mensajes = ctrl.obtener_mensajes(id_chat_1)
    assert len(mensajes) == 1
    assert mensajes[0]["remitente_tipo"] == "cliente"
    assert "Hola, quiero coordinar" in mensajes[0]["mensaje"]

    # 2. Listar chats: debe figurar en 'sin_atender'
    listado = ctrl.listar_chats()
    ids_sin_atender = [c["id_chat"] for c in listado["sin_atender"]]
    assert id_chat_1 in ids_sin_atender

    # 3. Operador 1 (id 1) toma el chat
    op1_id = 1
    op2_id = 2
    ok, msg = ctrl.tomar_chat(id_chat_1, id_usuario=op1_id, nombre_usuario="Admin FormoPack")
    assert ok is True

    # Chat ahora está en progreso
    chat_actualizado = ctrl.obtener_chat_por_id(id_chat_1)
    assert chat_actualizado["estado"] == "en_progreso"
    assert chat_actualizado["id_usuario_atendiendo"] == op1_id

    # Debe haberse enviado automáticamente el saludo del soporte
    mensajes_post = ctrl.obtener_mensajes(id_chat_1)
    assert len(mensajes_post) >= 2
    assert any(m["remitente_tipo"] == "soporte" for m in mensajes_post)

    # 4. REGLA: Un operador solo puede hablar con UN chat de cliente a la vez
    session_id_2 = f"test-session-2-{uuid.uuid4().hex[:10]}"
    chat_2 = ctrl.obtener_o_crear_chat(
        session_id=session_id_2,
        cliente_nombre="Maria Gomez",
        nro_guia="FPX-2026-OTRO",
        mensaje_inicial="Consulta sobre mi paquete",
    )
    id_chat_2 = chat_2["id_chat"]

    # El operador 1 (que ya tiene el chat 1 en progreso) intenta tomar el chat 2
    ok_intento, motivo = ctrl.tomar_chat(id_chat_2, id_usuario=op1_id, nombre_usuario="Admin FormoPack")
    assert ok_intento is False
    assert "Debés finalizarla antes de tomar otro chat" in motivo

    # 5. REGLA: Otro operador no puede intervenir si ya está siendo atendido
    ok_op2, motivo_op2 = ctrl.tomar_chat(id_chat_1, id_usuario=op2_id, nombre_usuario="Recepción Central")
    assert ok_op2 is False
    assert "ya está siendo atendido por" in motivo_op2

    # En cambio, Operador 2 SÍ puede tomar el chat 2 (porque está libre y Operador 2 no tiene chat)
    ok_op2_chat2, _ = ctrl.tomar_chat(id_chat_2, id_usuario=op2_id, nombre_usuario="Recepción Central")
    assert ok_op2_chat2 is True

    # 6. Envío de mensajes bidireccional
    ctrl.enviar_mensaje(id_chat_1, "soporte", "Admin FormoPack", "Podemos pasar a las 15 hs.")
    ctrl.enviar_mensaje(id_chat_1, "cliente", "Carlos Destinatario", "Perfecto, los espero.")

    mensajes_finales = ctrl.obtener_mensajes(id_chat_1)
    assert len(mensajes_finales) >= 4

    # 7. REGLA: Al terminar la conversación, debe eliminarse de la BD para no ocupar espacio
    eliminado_1 = ctrl.finalizar_chat(id_chat_1)
    assert eliminado_1 is True

    # Comprobar que ya no existe ni el chat ni sus mensajes en la BD
    assert ctrl.obtener_chat_por_id(id_chat_1) is None
    assert ctrl.obtener_mensajes(id_chat_1) == []

    # Y el Operador 1 ahora queda libre (no tiene ningún chat en progreso)
    assert ctrl.agente_tiene_chat_en_progreso(op1_id) is None

    # Limpiar chat 2
    ctrl.finalizar_chat(id_chat_2)
    assert ctrl.obtener_chat_por_id(id_chat_2) is None


def test_soporte_rutas_http(app_client):
    """Valida los endpoints HTTP para la mesa de soporte."""
    # 1. Acceso a /soporte/panel sin login debe redirigir a auth.login
    resp = app_client.get("/soporte/panel")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # 2. Iniciar chat desde API pública cliente
    resp_init = app_client.post("/soporte/api/iniciar", json={
        "cliente_nombre": "Test Cliente",
        "nro_guia": "FPX-999",
        "mensaje": "Mensaje de prueba"
    })
    assert resp_init.status_code == 200
    data_init = resp_init.get_json()
    assert data_init["ok"] is True
    session_id = data_init["session_id"]
    id_chat = data_init["id_chat"]

    # 3. Consultar mensajes desde la API pública
    resp_msg = app_client.get(f"/soporte/api/mensajes?session_id={session_id}")
    assert resp_msg.status_code == 200
    data_msg = resp_msg.get_json()
    assert data_msg["ok"] is True
    assert len(data_msg["mensajes"]) >= 1

    # 4. Enviar un nuevo mensaje desde el cliente
    resp_env = app_client.post("/soporte/api/enviar", json={
        "session_id": session_id,
        "mensaje": "Segundo mensaje del cliente"
    })
    assert resp_env.status_code == 200
    assert resp_env.get_json()["ok"] is True

    # 5. Finalizar chat desde la API pública (se elimina de la BD)
    resp_fin = app_client.post("/soporte/api/finalizar", json={"session_id": session_id})
    assert resp_fin.status_code == 200
    assert resp_fin.get_json()["ok"] is True

    # 6. Tras finalizar, consultar mensajes indica 'finalizado: True'
    resp_msg_post = app_client.get(f"/soporte/api/mensajes?session_id={session_id}")
    assert resp_msg_post.status_code == 200
    assert resp_msg_post.get_json()["finalizado"] is True
