"""Reglas de transición y reintento compartidas por los actores logísticos."""

from app.utils.exceptions import ValidationError


class EstadoEnvio:
    TERMINALES = {"entregado", "devolucion", "siniestro"}
    MAX_FALLOS = 3

    @classmethod
    def despachable(cls, estado, ruta_actual, fallos=0):
        return ruta_actual is None and fallos < cls.MAX_FALLOS and (estado in {"recibido", "en_planta"} or (estado == "fallido" and fallos > 0))

    @classmethod
    def validar_manual(cls, anterior, nuevo, rol, ruta_actual, fallos):
        if anterior in cls.TERMINALES:
            raise ValidationError("estado", "El envío está finalizado y no puede reabrirse desde este formulario")
        permitidos = {"recibido": {"en_planta", "siniestro"}, "en_planta": {"siniestro"},
                      "en_ruta": {"siniestro"}, "fallido": {"en_planta", "devolucion", "siniestro"}}
        if nuevo not in permitidos.get(anterior, set()):
            raise ValidationError("estado", "El cambio no corresponde al estado actual. La ruta se inicia desde el chofer y las entregas exigen su evidencia")
        if nuevo in {"siniestro", "devolucion"} and rol != "administrador":
            raise ValidationError("permiso", "La excepción requiere intervención de administración")
        if nuevo == "en_planta" and anterior == "fallido" and (ruta_actual is not None or fallos >= cls.MAX_FALLOS):
            raise ValidationError("estado", "El envío está en custodia o tiene una ruta pendiente. No admite otro intento domiciliario")
