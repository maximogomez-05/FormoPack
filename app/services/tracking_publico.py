"""Vista mínima del seguimiento por guía, sin datos personales completos."""


class TrackingPublico:
    UBICACIONES = {
        "recibido": "Sucursal de origen", "en_planta": "Centro de distribución",
        "devolucion": "Retorno a central", "retiro_remitente": "Central de Formosa Capital",
        "devuelto_remitente": "Central de Formosa Capital",
    }
    MOTIVOS = ("destinatario_ausente", "direccion_incorrecta", "rechazado", "zona_inaccesible")

    @staticmethod
    def iniciales(nombre):
        return " ".join(palabra[0] + "." for palabra in str(nombre or "").split()) or "Sin información"

    @classmethod
    def preparar(cls, envio, historial):
        if not envio:
            return None, []
        publico = {campo: envio.get(campo) for campo in
                   ("nro_guia", "estado_actual", "fecha_creacion", "cantidad_intentos", "localidad_destino")}
        publico["remitente"] = cls.iniciales(envio.get("remitente"))
        publico["destinatario"] = cls.iniciales(envio.get("destinatario"))
        publico["ubicacion_gps"] = envio.get("ubicacion_gps") if envio.get("estado_actual") == "en_ruta" else None
        eventos = []
        for evento in historial or []:
            estado = evento.get("estado")
            observacion = str(evento.get("observacion") or "").lower()
            motivo = next((m for m in cls.MOTIVOS if m in observacion), "") if estado == "fallido" else ""
            eventos.append({"estado": estado, "fecha_hora": evento.get("fecha_hora") or evento.get("fecha"),
                            "ubicacion": cls.UBICACIONES.get(estado, envio.get("localidad_destino") or "Centro de distribución"),
                            "observacion": motivo})
        return publico, eventos
