"""Datos ficticios aditivos para una demostración en el sistema publicado."""

import hashlib
from datetime import datetime, timedelta

from werkzeug.datastructures import MultiDict

from app.controllers.envio_controller import EnvioController
from app.models.solicitud_recepcion import SolicitudRecepcion
from app.services.geografia_destino import CENTROS_LOCALIDAD
from app.utils.exceptions import ValidationError


class DatosDemostracion:
    def __init__(self, db):
        self.db = db

    def cargar(self, administrador):
        servicio = EnvioController(self.db)
        guias = []
        with self.db.cursor(dictionary=False) as cur:
            cur.execute("SELECT activo, tipo_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (administrador,))
            if cur.fetchone() != (1, "administrador"):
                raise ValidationError("cuenta", "Se requiere una cuenta administradora activa")
            cur.execute("SELECT id_localidad,nombre FROM localidades ORDER BY id_localidad LIMIT 7")
            localidades = cur.fetchall()
            if not localidades:
                raise ValidationError("localidades", "Primero deben existir localidades")
            for indice in range(14):
                localidad = localidades[indice % len(localidades)]
                centro = next((coordenadas for nombre, coordenadas in CENTROS_LOCALIDAD.items()
                    if nombre.casefold() == localidad["nombre"].casefold()), None)
                if centro is None:
                    raise ValidationError("localidades", "La localidad de demostración no tiene coordenadas configuradas")
                clave = hashlib.sha256(f"demostracion-inicial-v1-{indice}".encode()).hexdigest()[:32]
                cur.execute("""INSERT INTO solicitudes_mostrador (id_usuario, solicitud_id)
                    VALUES (%s,%s) ON DUPLICATE KEY UPDATE solicitud_id=VALUES(solicitud_id)""", (administrador, clave))
                cur.execute("SELECT id_envio FROM solicitudes_mostrador WHERE id_usuario=%s AND solicitud_id=%s",
                            (administrador, clave))
                if cur.fetchone()[0]:
                    continue
                solicitud = SolicitudRecepcion(MultiDict({
                    "rem_dni": "90000001", "rem_nombre": "Remitente Demo", "rem_telefono": "0000000000",
                    "dest_dni": f"90000{indice+2:03d}", "dest_nombre": "Destinatario Demo",
                    "dest_telefono": "0000000000", "direccion_destino": "Dirección ficticia para demostración",
                    "id_localidad_destino": str(localidad["id_localidad"]),
                    "destino_latitud": str(centro[0]), "destino_longitud": str(centro[1]),
                    "peso_real[]": str(indice % 8 + 1), "peso_volumetrico[]": "0",
                    "modalidad_pago": "efectivo",
                }))
                clientes = []
                for rol in ("rem", "dest"):
                    datos = solicitud.clientes[rol]
                    cur.execute("SELECT id_cliente, nombre_completo, telefono, email FROM clientes WHERE dni=%s FOR UPDATE",
                                (datos["dni"],))
                    existente = cur.fetchone()
                    if existente:
                        if existente[1:] != (datos["nombre_completo"], datos["telefono"], None):
                            raise ValidationError("demo", "Un documento de ejemplo ya está usado por otro cliente")
                        clientes.append(existente[0])
                    else:
                        cur.execute("INSERT INTO clientes (dni,nombre_completo,telefono) VALUES (%s,%s,%s)",
                                    (datos["dni"], datos["nombre_completo"], datos["telefono"]))
                        clientes.append(cur.lastrowid)
                cotizacion = servicio.cotizar_envio(solicitud.bultos, solicitud.localidad)
                resultado = servicio._insertar_envio(cur, *clientes, solicitud.localidad, solicitud.direccion,
                    solicitud.bultos, solicitud.modalidad, solicitud.declarado, solicitud.seguro, cotizacion)
                fecha = datetime.now() - timedelta(days=indice % 7)
                cur.execute("UPDATE envios SET fecha_creacion=%s WHERE id_envio=%s", (fecha, resultado["id_envio"]))
                cur.execute("""UPDATE historial_estados SET fecha_hora=%s,
                    observacion='DEMO: envío ficticio pendiente de cobro para presentación académica.'
                    WHERE id_envio=%s""", (fecha, resultado["id_envio"]))
                cur.execute("UPDATE comprobantes_internos SET fecha_emision=%s WHERE id_envio=%s",
                            (fecha, resultado["id_envio"]))
                cur.execute("UPDATE solicitudes_mostrador SET id_envio=%s WHERE id_usuario=%s AND solicitud_id=%s",
                            (resultado["id_envio"], administrador, clave))
                guias.append(resultado["nro_guia"])
        return guias
