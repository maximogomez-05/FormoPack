"""Despacho y resolución de visitas con bloqueos y trazabilidad compartidos."""

import logging
import re
from contextlib import contextmanager

from app.core.database import DatabaseManager
from app.models.estado_envio import EstadoEnvio
from app.models.hoja_ruta import HojaRuta
from app.models.prueba_entrega import PruebaDeEntrega, EntregaFallida
from app.services.validacion_entrada import ValidacionEntrada as V
from app.services.servicio_notificacion import notificar_cambio_estado_async
from app.utils.exceptions import ValidationError, DatabaseQueryError, DuplicateError

logger = logging.getLogger(__name__)


class OperacionesLogisticas:
    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager.get_instance()

    @contextmanager
    def _transaccion(self):
        conn, cur = None, None
        try:
            conn = self.db.get_connection()
            cur = conn.cursor(dictionary=True)
            yield cur
            conn.commit()
        except (ValidationError, DuplicateError):
            if conn: conn.rollback()
            raise
        except Exception as exc:
            if conn: conn.rollback()
            if getattr(exc, "errno", None) == 1062:
                raise DuplicateError("Despacho o recurso", "ya asignado") from exc
            logger.error("No se pudo guardar una operación logística", exc_info=True)
            raise DatabaseQueryError("No se pudo completar la operación logística. Consultá el estado antes de reintentar.") from exc
        finally:
            if cur: cur.close()
            if conn: conn.close()

    @staticmethod
    def _actor(cur, id_usuario, roles):
        cur.execute("SELECT id_usuario,tipo_usuario,activo FROM usuarios WHERE id_usuario=%s FOR UPDATE", (id_usuario,))
        actor = cur.fetchone()
        if not actor or not actor["activo"] or actor["tipo_usuario"] not in roles:
            raise ValidationError("usuario", "La cuenta no está habilitada para esta operación")
        return actor

    @staticmethod
    def _ruta(cur, id_ruta):
        cur.execute("SELECT id_chofer,id_vehiculo FROM hojas_de_ruta WHERE id_hoja_ruta=%s", (id_ruta,))
        datos = cur.fetchone()
        if not datos:
            raise ValidationError("hoja_ruta", "La hoja de ruta no existe")
        # Orden de bloqueo común: chofer, vehículo, hoja y envíos.
        cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (datos["id_chofer"],))
        cur.fetchone()
        cur.execute("SELECT id_vehiculo,estado FROM vehiculos WHERE id_vehiculo=%s FOR UPDATE", (datos["id_vehiculo"],))
        movil = cur.fetchone()
        cur.execute("SELECT * FROM hojas_de_ruta WHERE id_hoja_ruta=%s FOR UPDATE", (id_ruta,))
        ruta = cur.fetchone()
        ruta["estado_vehiculo"] = movil["estado"] if movil else None
        return ruta

    @staticmethod
    def _historial(cur, envio, estado, actor, ubicacion, observacion):
        cur.execute("""INSERT INTO historial_estados (id_envio,estado,id_usuario_actor,ubicacion,observacion)
            VALUES (%s,%s,%s,%s,%s)""", (envio, estado, actor, ubicacion, observacion))

    @staticmethod
    def _avisar(eventos):
        for envio, estado, observacion in eventos:
            try:
                notificar_cambio_estado_async(envio, nuevo_estado=estado, observacion=observacion)
            except Exception:
                # Un fallo de correo posterior al commit no deshace la operación guardada.
                logger.warning("Aviso logístico pendiente de envío: #%s", envio)

    @staticmethod
    def _fallos(cur, envio):
        cur.execute("SELECT id_intento FROM intentos_entrega WHERE id_envio=%s AND tipo_intento='fallido' FOR UPDATE", (envio,))
        return len(cur.fetchall())

    @staticmethod
    def _cerrar_si_resuelta(cur, ruta):
        cur.execute("SELECT resolucion FROM hojas_ruta_envios WHERE id_hoja_ruta=%s ORDER BY id_envio FOR UPDATE", (ruta["id_hoja_ruta"],))
        asignaciones = cur.fetchall()
        if not asignaciones or any(a["resolucion"] is None for a in asignaciones):
            return False
        cur.execute("UPDATE hojas_de_ruta SET estado='cerrada',fecha_cierre=NOW() WHERE id_hoja_ruta=%s AND estado='abierta'", (ruta["id_hoja_ruta"],))
        if cur.rowcount:
            cur.execute("UPDATE vehiculos SET estado='disponible' WHERE id_vehiculo=%s AND estado IN ('en_ruta','reservado')", (ruta["id_vehiculo"],))
        return True

    def crear(self, despacho, chofer, vehiculo, envios, actor):
        despacho = V.texto(despacho, "nro_despacho", 1, 20)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", despacho):
            raise ValidationError("nro_despacho", "Usá letras, números, guiones o guion bajo")
        chofer, vehiculo, actor = V.entero(chofer, "chofer"), V.entero(vehiculo, "vehiculo"), V.entero(actor, "usuario")
        if not isinstance(envios, list) or not 1 <= len(envios) <= 100:
            raise ValidationError("envios", "Seleccioná entre 1 y 100 envíos")
        ids = sorted(V.entero(i, "envio") for i in envios)
        if len(set(ids)) != len(ids):
            raise ValidationError("envios", "No repitas un envío dentro del despacho")
        eventos = []
        with self._transaccion() as cur:
            self._actor(cur, actor, {"administrador"})
            self._actor(cur, chofer, {"chofer"})
            cur.execute("SELECT * FROM vehiculos WHERE id_vehiculo=%s FOR UPDATE", (vehiculo,))
            movil = cur.fetchone()
            if not movil or movil["estado"] != "disponible":
                raise ValidationError("vehiculo", "El vehículo no está disponible")
            cur.execute("SELECT id_hoja_ruta FROM hojas_de_ruta WHERE estado='abierta' AND (id_chofer=%s OR id_vehiculo=%s)", (chofer, vehiculo))
            if cur.fetchall():
                raise ValidationError("despacho", "El chofer o vehículo ya tiene una hoja abierta")
            seleccion = []
            for id_envio in ids:
                cur.execute("SELECT * FROM envios WHERE id_envio=%s FOR UPDATE", (id_envio,))
                envio = cur.fetchone()
                fallos = self._fallos(cur, id_envio)
                if not envio or not EstadoEnvio.despachable(envio["estado_actual"], envio["id_hoja_ruta"], fallos):
                    raise ValidationError("envio", "El envío no está disponible, ya está asignado o agotó sus intentos")
                cur.execute("""SELECT h.id_hoja_ruta FROM hojas_ruta_envios a JOIN hojas_de_ruta h ON h.id_hoja_ruta=a.id_hoja_ruta
                    WHERE a.id_envio=%s AND h.estado='abierta'""", (id_envio,))
                if cur.fetchall():
                    raise ValidationError("envio", "La ruta anterior todavía no terminó. Confirmá su cierre antes de reprogramar")
                cur.execute("SELECT peso_real FROM bultos WHERE id_envio=%s FOR UPDATE", (id_envio,))
                bultos = cur.fetchall()
                if not bultos or any(b["peso_real"] <= 0 for b in bultos):
                    raise ValidationError("bultos", "El envío tiene pesos incompletos o inválidos")
                envio["peso"] = sum(b["peso_real"] for b in bultos)
                cur.execute("SELECT nombre AS localidad_destino,distancia_km FROM localidades WHERE id_localidad=%s", (envio["id_localidad_destino"],))
                envio.update(cur.fetchone())
                seleccion.append(envio)
            if sum(e["peso"] for e in seleccion) > movil["capacidad_kg"]:
                raise ValidationError("capacidad", "La carga supera la capacidad del vehículo")
            cur.execute("INSERT INTO hojas_de_ruta (nro_despacho,id_chofer,id_vehiculo) VALUES (%s,%s,%s)", (despacho, chofer, vehiculo))
            id_ruta = cur.lastrowid
            cur.execute("SELECT fecha_emision FROM hojas_de_ruta WHERE id_hoja_ruta=%s", (id_ruta,))
            fecha = cur.fetchone()["fecha_emision"]
            for envio in seleccion:
                cur.execute("INSERT INTO hojas_ruta_envios (id_hoja_ruta,id_envio) VALUES (%s,%s)", (id_ruta, envio["id_envio"]))
                cur.execute("UPDATE envios SET id_hoja_ruta=%s,estado_actual='en_planta' WHERE id_envio=%s", (id_ruta, envio["id_envio"]))
                self._historial(cur, envio["id_envio"], "en_planta", actor, "Depósito", "Asignado a hoja de ruta")
                eventos.append((envio["id_envio"], "en_planta", "Asignado a hoja de ruta"))
                envio["estado_actual"] = "en_planta"
            cur.execute("UPDATE vehiculos SET estado='reservado' WHERE id_vehiculo=%s", (vehiculo,))
        self._avisar(eventos)
        return HojaRuta(id_ruta, despacho, chofer, vehiculo, fecha_emision=fecha, envios=seleccion)

    def iniciar(self, chofer, ruta_id):
        chofer, ruta_id = V.entero(chofer, "chofer"), V.entero(ruta_id, "hoja")
        eventos = []
        with self._transaccion() as cur:
            self._actor(cur, chofer, {"chofer"})
            ruta = self._ruta(cur, ruta_id)
            if ruta["id_chofer"] != chofer or ruta["estado"] != "abierta":
                raise ValidationError("hoja", "La hoja no está abierta o no pertenece al chofer")
            if ruta["fecha_inicio"] is not None:
                return
            if ruta["estado_vehiculo"] not in {"reservado", "en_ruta"}:
                raise ValidationError("vehiculo", "El vehículo asignado no está habilitado para iniciar")
            cur.execute("""SELECT e.id_envio,e.estado_actual FROM envios e
                JOIN hojas_ruta_envios a ON a.id_envio=e.id_envio AND a.id_hoja_ruta=e.id_hoja_ruta
                WHERE e.id_hoja_ruta=%s AND a.resolucion IS NULL ORDER BY e.id_envio FOR UPDATE""", (ruta_id,))
            envios = cur.fetchall()
            if not envios or any(e["estado_actual"] not in {"recibido", "en_planta", "en_ruta"} for e in envios):
                raise ValidationError("hoja", "La hoja contiene envíos que requieren revisión antes de iniciar")
            cur.execute("UPDATE hojas_de_ruta SET fecha_inicio=NOW() WHERE id_hoja_ruta=%s", (ruta_id,))
            cur.execute("UPDATE vehiculos SET estado='en_ruta' WHERE id_vehiculo=%s", (ruta["id_vehiculo"],))
            for envio in envios:
                cur.execute("UPDATE envios SET estado_actual='en_ruta' WHERE id_envio=%s", (envio["id_envio"],))
                self._historial(cur, envio["id_envio"], "en_ruta", chofer, "En ruta", "Ruta iniciada por el chofer")
                eventos.append((envio["id_envio"], "en_ruta", "Ruta iniciada por el chofer"))
        self._avisar(eventos)

    def entregar(self, chofer, ruta_id, envio_id, tipo_intento, dni_receptor=None, firma_receptor=None, foto_remito=None, coordenadas_gps=None, motivo_fallo=None):
        chofer, ruta_id, envio_id = V.entero(chofer, "chofer"), V.entero(ruta_id, "hoja"), V.entero(envio_id, "envio")
        prueba_cls = EntregaFallida if tipo_intento == "fallido" else PruebaDeEntrega
        prueba = prueba_cls(id_intento=None, id_envio=envio_id, id_hoja_ruta=ruta_id, tipo_intento=tipo_intento,
            dni_receptor=dni_receptor, firma_receptor=firma_receptor, foto_remito=foto_remito, coordenadas_gps=coordenadas_gps, motivo_fallo=motivo_fallo)
        prueba.validar_entrega()
        if tipo_intento == "fallido" and motivo_fallo not in {"destinatario_ausente", "domicilio_incorrecto", "rechazo", "otro"}:
            raise ValidationError("motivo", "Seleccioná un motivo de fallo válido")
        if tipo_intento == "entregado":
            V.documento(dni_receptor)
        eventos = []
        with self._transaccion() as cur:
            self._actor(cur, chofer, {"chofer"})
            ruta = self._ruta(cur, ruta_id)
            if ruta["id_chofer"] != chofer or ruta["estado"] != "abierta" or ruta["fecha_inicio"] is None:
                raise ValidationError("hoja", "Iniciá tu ruta antes de registrar el resultado")
            cur.execute("SELECT estado_actual,id_hoja_ruta FROM envios WHERE id_envio=%s FOR UPDATE", (envio_id,))
            envio = cur.fetchone()
            if not envio or envio["id_hoja_ruta"] != ruta_id or envio["estado_actual"] != "en_ruta":
                raise ValidationError("envio", "El envío ya fue resuelto o no pertenece a esta ruta")
            cur.execute("SELECT resolucion FROM hojas_ruta_envios WHERE id_hoja_ruta=%s AND id_envio=%s FOR UPDATE", (ruta_id, envio_id))
            asignacion = cur.fetchone()
            if not asignacion or asignacion["resolucion"] is not None or self._fallos(cur, envio_id) >= EstadoEnvio.MAX_FALLOS:
                raise ValidationError("intento", "La visita ya se registró o el envío está en custodia")
            cur.execute("""INSERT INTO intentos_entrega (id_envio,id_hoja_ruta,tipo_intento,dni_receptor,firma_receptor,foto_remito,coordenadas_gps,motivo_fallo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (envio_id, ruta_id, tipo_intento, dni_receptor, firma_receptor, foto_remito, coordenadas_gps, motivo_fallo))
            cur.execute("UPDATE hojas_ruta_envios SET resolucion=%s,fecha_resolucion=NOW() WHERE id_hoja_ruta=%s AND id_envio=%s", (tipo_intento, ruta_id, envio_id))
            cur.execute("UPDATE envios SET estado_actual=%s,id_hoja_ruta=%s WHERE id_envio=%s", (tipo_intento, None if tipo_intento == "fallido" else ruta_id, envio_id))
            texto = "Entrega confirmada por el chofer" if tipo_intento == "entregado" else f"Visita fallida: {motivo_fallo}. Revisión en depósito."
            self._historial(cur, envio_id, tipo_intento, chofer, coordenadas_gps or "Sin ubicación", texto)
            self._cerrar_si_resuelta(cur, ruta)
            eventos.append((envio_id, tipo_intento, texto))
        self._avisar(eventos)

    def actualizar_manual(self, envio_id, nuevo, actor_id, ubicacion, observacion):
        actor_id, envio_id = V.entero(actor_id, "usuario"), V.entero(envio_id, "envio")
        ubicacion = V.texto(ubicacion, "ubicacion", 1, 100)
        observacion = V.texto(observacion, "observacion", 3, 1000)
        with self._transaccion() as cur:
            actor = self._actor(cur, actor_id, {"administrador", "recepcionista"})
            cur.execute("SELECT id_hoja_ruta FROM envios WHERE id_envio=%s", (envio_id,))
            previo = cur.fetchone()
            if not previo:
                raise ValidationError("envio", "El envío no existe")
            ruta = self._ruta(cur, previo["id_hoja_ruta"]) if previo["id_hoja_ruta"] else None
            cur.execute("SELECT * FROM envios WHERE id_envio=%s FOR UPDATE", (envio_id,))
            envio = cur.fetchone()
            if envio["id_hoja_ruta"] != previo["id_hoja_ruta"]:
                raise ValidationError("envio", "La asignación cambió. Actualizá el panel antes de reintentar")
            EstadoEnvio.validar_manual(envio["estado_actual"], nuevo, actor["tipo_usuario"], envio["id_hoja_ruta"], self._fallos(cur, envio_id))
            cur.execute("UPDATE envios SET estado_actual=%s,es_devolucion=%s WHERE id_envio=%s", (nuevo, int(nuevo == "devolucion"), envio_id))
            self._historial(cur, envio_id, nuevo, actor_id, ubicacion, observacion)
            if ruta and nuevo in EstadoEnvio.TERMINALES:
                cur.execute("UPDATE hojas_ruta_envios SET resolucion=%s,fecha_resolucion=NOW() WHERE id_hoja_ruta=%s AND id_envio=%s AND resolucion IS NULL", (nuevo, ruta["id_hoja_ruta"], envio_id))
                self._cerrar_si_resuelta(cur, ruta)
        self._avisar([(envio_id, nuevo, observacion)])
