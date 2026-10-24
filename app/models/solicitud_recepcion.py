"""Datos validados de recepción antes de crear clientes o envíos."""

from app.models.bulto import Bulto
from app.models.cliente import Cliente
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import ValidationError


class SolicitudRecepcion:
    MODALIDADES = {"efectivo", "digital", "cuenta_corriente"}

    @classmethod
    def validar_envio(cls, direccion, modalidad):
        direccion = V.texto(direccion, "direccion_destino", 3, 200)
        if not any(c.isalpha() for c in direccion):
            raise ValidationError("direccion_destino", "Ingresá una dirección que incluya calle, barrio o referencia")
        if not isinstance(modalidad, str) or modalidad not in cls.MODALIDADES:
            raise ValidationError("modalidad_pago", "Seleccioná una modalidad de pago válida")
        return direccion

    @staticmethod
    def validar_cotizacion(bultos, localidad, declarado=0, seguro=None):
        datos = Bulto.validar_lista(bultos)
        localidad = V.entero(localidad, "id_localidad_destino")
        declarado = V.decimal(declarado, "valor_declarado")
        seguro = V.entero(seguro, "id_seguro") if seguro not in (None, "") else None
        if seguro and declarado <= 0:
            raise ValidationError("valor_declarado", "El seguro requiere un valor declarado mayor que cero")
        return datos, localidad, declarado, seguro

    def __init__(self, formulario):
        self.clientes = {}
        for prefijo in ("rem", "dest"):
            datos = {"dni": formulario.get(prefijo + "_dni", ""),
                     "nombre_completo": formulario.get(prefijo + "_nombre", ""),
                     "telefono": formulario.get(prefijo + "_telefono", ""),
                     "email": formulario.get(prefijo + "_email")}
            Cliente.validar_datos(**datos)
            self.clientes[prefijo] = datos
        pesos = formulario.getlist("peso_real[]")
        volumenes = formulario.getlist("peso_volumetrico[]")
        if not 1 <= len(pesos) <= 100:
            raise ValidationError("bultos", "Ingresá entre 1 y 100 bultos por envío")
        if len(pesos) != len(volumenes):
            raise ValidationError("bultos", "Faltan pesos de alguno de los bultos")
        fragiles = formulario.getlist("es_fragil[]")
        if len(set(fragiles)) != len(fragiles) or any(i not in {str(n) for n in range(len(pesos))} for i in fragiles):
            raise ValidationError("es_fragil", "Revisá las marcas de fragilidad de los bultos")
        datos = [{"peso_real": peso, "peso_volumetrico": volumenes[i] or "0", "es_fragil": str(i) in fragiles}
                 for i, peso in enumerate(pesos)]
        self.bultos, self.localidad, self.declarado, self.seguro = self.validar_cotizacion(
            datos, formulario.get("id_localidad_destino"), formulario.get("valor_declarado") or "0", formulario.get("id_seguro"))
        self.modalidad = formulario.get("modalidad_pago", "efectivo")
        self.direccion = self.validar_envio(formulario.get("direccion_destino", ""), self.modalidad)
