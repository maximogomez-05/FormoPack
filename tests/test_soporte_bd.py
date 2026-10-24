"""RF 5.6 con InnoDB y concurrencia en una instancia desechable opt-in."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import mysql.connector
import pytest

from app.controllers.soporte_controller import SoporteController
from app.core.migrations import MigrationManager
from app.utils.exceptions import SoporteError, DatabaseQueryError
from tests.test_seguridad_bd import db, ROOT


class TestSoportePersistente:
    def test_inicio_sin_mensaje_es_valido(self, db):
        token = uuid.uuid4().hex + uuid.uuid4().hex
        ctrl = SoporteController(db)
        chat = ctrl.iniciar_chat(token, "Cliente")
        assert chat["estado"] == "sin_atender"
        assert ctrl.consultar_cliente(token)[1] == []

    @staticmethod
    def iniciar(db, nombre="Cliente"):
        token = uuid.uuid4().hex + uuid.uuid4().hex
        chat = SoporteController(db).iniciar_chat(token, nombre, "cliente@example.com", mensaje="Consulta inicial")
        return chat["id_chat"], token

    @staticmethod
    def operador(db):
        with db.cursor() as cur:
            cur.execute("""INSERT INTO usuarios (nombre, email, credenciales_hash, tipo_usuario)
                VALUES ('Otro operador', 'otro@example.com', 'hash-prueba', 'recepcionista')""")
            return cur.lastrowid

    def test_ciclo_completo_con_historial_y_purga(self, db):
        ctrl = SoporteController(db)
        id_chat, token = self.iniciar(db)
        ctrl.tomar_chat(id_chat, 2)
        ctrl.tomar_chat(id_chat, 2)
        ctrl.enviar_staff(id_chat, 2, "Respuesta del operador")
        ctrl.enviar_cliente(token, "Muchas gracias")
        chat, mensajes = ctrl.consultar_cliente(token)
        assert chat["estado"] == "en_progreso" and "session_id" not in chat
        assert len(mensajes) == 4  # inicial, bienvenida única y dos respuestas
        ctrl.finalizar_staff(id_chat, 2)
        chat, mensajes = ctrl.consultar_cliente(token)
        assert chat["estado"] == "cerrado" and mensajes == []
        assert chat["id_usuario_atendiendo"] == 2 and chat["id_usuario_cierre"] == 2
        fecha_cierre = chat["fecha_cierre"]
        ctrl.finalizar_staff(id_chat, 2)
        assert ctrl.consultar_cliente(token)[0]["fecha_cierre"] == fecha_cierre
        assert ctrl.agente_tiene_chat_en_progreso(2) is None
        with pytest.raises(SoporteError):
            ctrl.enviar_staff(id_chat, 2, "No debe guardarse")
        with pytest.raises(SoporteError):
            ctrl.enviar_cliente(token, "No debe guardarse")

    def test_permisos_autoritativos_en_servidor(self, db):
        otro = self.operador(db)
        ctrl = SoporteController(db)
        id_chat, token = self.iniciar(db)
        ctrl.tomar_chat(id_chat, 2)
        for accion in (
            lambda: ctrl.enviar_staff(id_chat, otro, "Intrusión"),
            lambda: ctrl.finalizar_staff(id_chat, otro),
            lambda: ctrl.consultar_staff(id_chat, otro),
            lambda: ctrl.tomar_chat(id_chat, otro),
            lambda: ctrl.tomar_chat(id_chat, 3),  # chofer
        ):
            with pytest.raises(SoporteError):
                accion()
        chat, mensajes = ctrl.consultar_staff(id_chat, 1)
        assert len(mensajes) == 2  # el administrador puede supervisar
        with pytest.raises(SoporteError):
            ctrl.enviar_staff(id_chat, 1, "Interferencia")
        ctrl.finalizar_staff(id_chat, 1)
        assert ctrl.consultar_cliente(token)[0]["id_usuario_cierre"] == 1

    def test_dos_operadores_compiten_por_un_chat(self, db):
        otro = self.operador(db)
        id_chat, token = self.iniciar(db)
        barrera = Barrier(2)

        def tomar(id_usuario):
            barrera.wait(timeout=10)
            try:
                SoporteController(db).tomar_chat(id_chat, id_usuario)
                return True
            except SoporteError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(tomar, [2, otro])) == [False, True]
        chat, mensajes = SoporteController(db).consultar_cliente(token)
        assert chat["id_usuario_atendiendo"] in (2, otro)
        assert len(mensajes) == 2

    def test_operador_compite_por_dos_chats(self, db):
        ids = [self.iniciar(db)[0], self.iniciar(db)[0]]
        barrera = Barrier(2)

        def tomar(id_chat):
            barrera.wait(timeout=10)
            try:
                SoporteController(db).tomar_chat(id_chat, 2)
                return True
            except SoporteError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(tomar, ids)) == [False, True]
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM chats_soporte WHERE operador_activo=2")
            assert cur.fetchone()["total"] == 1

    def test_base_impide_asignacion_duplicada_aunque_se_omita_controlador(self, db):
        primero, _ = self.iniciar(db)
        segundo, _ = self.iniciar(db)
        SoporteController(db).tomar_chat(primero, 2)
        with pytest.raises(mysql.connector.IntegrityError):
            with db.cursor() as cur:
                cur.execute("UPDATE chats_soporte SET estado='en_progreso',id_usuario_atendiendo=2 WHERE id_chat=%s", (segundo,))

    def test_inicio_concurrente_es_idempotente(self, db):
        token = uuid.uuid4().hex + uuid.uuid4().hex
        barrera = Barrier(4)

        def iniciar(_):
            barrera.wait(timeout=10)
            return SoporteController(db).iniciar_chat(token, "Cliente", mensaje="Consulta inicial")["id_chat"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert len(set(pool.map(iniciar, range(4)))) == 1
        assert len(SoporteController(db).consultar_cliente(token)[1]) == 1

    def test_cierre_concurrente_con_respuesta_no_deja_mensajes(self, db):
        id_chat, token = self.iniciar(db)
        ctrl = SoporteController(db)
        ctrl.tomar_chat(id_chat, 2)
        barrera = Barrier(2)

        def enviar():
            barrera.wait(timeout=10)
            try:
                SoporteController(db).enviar_staff(id_chat, 2, "Respuesta")
            except SoporteError as error:
                assert error.code == "CHAT_CLOSED"

        def cerrar():
            barrera.wait(timeout=10)
            SoporteController(db).finalizar_cliente(token)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [pool.submit(enviar), pool.submit(cerrar)]
            for futuro in futuros:
                futuro.result(timeout=15)
        assert ctrl.consultar_cliente(token)[0]["estado"] == "cerrado"
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM mensajes_soporte WHERE id_chat=%s", (id_chat,))
            assert cur.fetchone()["total"] == 0

    def test_cierre_revierte_purga_si_falla_actualizacion(self, db):
        id_chat, token = self.iniciar(db)
        with db.cursor(False) as cur:
            cur.execute("CREATE TRIGGER fallo_cierre BEFORE UPDATE ON chats_soporte FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fallo de prueba'")
        with pytest.raises(DatabaseQueryError):
            SoporteController(db).finalizar_cliente(token)
        chat, mensajes = SoporteController(db).consultar_cliente(token)
        assert chat["estado"] == "sin_atender" and len(mensajes) == 1

    def test_panel_no_filtra_mensajes_ajenos(self, db):
        otro = self.operador(db)
        id_chat, _ = self.iniciar(db)
        ctrl = SoporteController(db)
        ctrl.tomar_chat(id_chat, 2)
        filas = ctrl.listar_chats(otro)["en_progreso"]
        assert filas[0]["ultimo_mensaje"] is None
        assert not filas[0]["puede_ver"] and not filas[0]["puede_finalizar"]
        assert "session_id" not in filas[0]

    def test_baja_logica_conserva_historial(self, db):
        id_chat, token = self.iniciar(db)
        ctrl = SoporteController(db)
        ctrl.tomar_chat(id_chat, 2)
        ctrl.finalizar_staff(id_chat, 2)
        with db.cursor() as cur:
            cur.execute("UPDATE usuarios SET activo=0 WHERE id_usuario=2")
        assert ctrl.consultar_cliente(token)[0]["id_usuario_atendiendo"] == 2

    def test_migracion_repetida_no_reabre_chat_cerrado(self, db):
        id_chat, token = self.iniciar(db)
        SoporteController(db).finalizar_cliente(token)
        db.ejecutar_archivo(ROOT / "scripts/migrations/006_soporte_exclusivo.sql")
        assert SoporteController(db).consultar_cliente(token)[0]["estado"] == "cerrado"

    def test_migracion_no_reasigna_duplicados_sin_resolver(self, db):
        primero, _ = self.iniciar(db)
        segundo, _ = self.iniciar(db)
        with db.cursor() as cur:
            cur.execute("ALTER TABLE chats_soporte DROP INDEX uk_soporte_operador_activo")
            cur.execute("DELETE FROM schema_migrations WHERE version='006_soporte_exclusivo'")
            cur.execute("UPDATE chats_soporte SET estado='en_progreso',id_usuario_atendiendo=2 WHERE id_chat IN (%s,%s)", (primero, segundo))
        with pytest.raises(ValueError, match="varios chats activos"):
            MigrationManager(db).aplicar_migraciones(desde="006")
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM chats_soporte WHERE estado='en_progreso'")
            assert cur.fetchone()["total"] == 2
