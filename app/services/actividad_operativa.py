"""Presentación compacta del período sin eliminar sus días de referencia."""


class ActividadOperativa:
    def __init__(self, dias):
        self.dias = dias
        self.con_movimiento = [dia for dia in dias if any(
            dia.get(campo, 0) > 0 for campo in ("total_envios", "entregados", "fallidos", "facturado"))]

    def filas(self, mostrar_todos=False):
        return self.dias if mostrar_todos else self.con_movimiento
