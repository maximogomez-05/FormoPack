"""Datos validados de recepción antes de crear clientes o envíos."""

import re

from app.models.bulto import Bulto
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import ValidationError


class SolicitudRecepcion:
    MODALIDADES = {"efectivo", "digital", "cuenta_corriente"}
    PRIORIDADES = {"normal", "alta", "urgente"}

    @classmethod
    def validar_datos_planificacion(cls, latitud, longitud, ventana_desde, ventana_hasta, prioridad="normal"):
        if (latitud in (None, "")) != (longitud in (None, "")):
            raise ValidationError("destino", "Marcá el punto de entrega completo en el mapa")
        if latitud in (None, ""):
            latitud_validada = longitud_validada = None
        else:
            latitud_validada = V.medicion(latitud, "destino_latitud", -90, 90, 7)
            longitud_validada = V.medicion(longitud, "destino_longitud", -180, 180, 7)

        ventana_desde = cls._validar_hora(ventana_desde, "ventana_desde")
        ventana_hasta = cls._validar_hora(ventana_hasta, "ventana_hasta")
        if (ventana_desde is None) != (ventana_hasta is None):
            raise ValidationError("ventana", "Completá las dos horas de la ventana de entrega")
        if ventana_desde and ventana_desde >= ventana_hasta:
            raise ValidationError("ventana", "La hora final debe ser posterior a la inicial")
        prioridad = str(prioridad or "normal").strip().lower()
        if prioridad not in cls.PRIORIDADES:
            raise ValidationError("prioridad", "Seleccioná una prioridad válida")
        return latitud_validada, longitud_validada, ventana_desde, ventana_hasta, prioridad

    @staticmethod
    def _validar_hora(valor, campo):
        if valor in (None, ""):
            return None
        texto = str(valor).strip()
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", texto):
            raise ValidationError(campo, "Ingresá una hora válida")
        return texto + ":00"

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
        V.campos_unicos(formulario, ("peso_real[]", "peso_volumetrico[]", "es_fragil[]"))
        self.clientes = {}
        for prefijo in ("rem", "dest"):
            datos = {"dni": formulario.get(prefijo + "_dni", ""),
                     "nombre_completo": formulario.get(prefijo + "_nombre", ""),
                     "telefono": formulario.get(prefijo + "_telefono", ""),
                     "email": formulario.get(prefijo + "_email")}
            datos = {"dni": V.documento(datos["dni"]),
                     "nombre_completo": V.nombre(datos["nombre_completo"]),
                     "telefono": V.telefono(datos["telefono"]),
                     "email": V.email(datos["email"])}
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
        (self.destino_latitud, self.destino_longitud, self.ventana_desde,
         self.ventana_hasta, self.prioridad) = self.validar_datos_planificacion(
            formulario.get("destino_latitud"), formulario.get("destino_longitud"),
            formulario.get("ventana_desde"), formulario.get("ventana_hasta"),
            formulario.get("prioridad", "normal"),
        )
        if self.destino_latitud is None or self.destino_longitud is None:
            raise ValidationError("direccion_destino", "Seleccioná una dirección sugerida o marcá el punto en el mapa para validar el domicilio")
