"""Validaciones de entrada previas a la persistencia, con límites del esquema."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.utils.exceptions import ValidationError


class ValidacionEntrada:
    MAX_IMPORTE = Decimal("9999999999.99")  # DECIMAL(12,2)
    MAX_PESO = Decimal("999999.99")  # DECIMAL(8,2)

    @staticmethod
    def texto(valor, campo, minimo, maximo):
        if not isinstance(valor, str) or any(unicodedata.category(c).startswith("C") for c in valor):
            raise ValidationError(campo, "Ingresá un texto válido, sin caracteres de control")
        texto = unicodedata.normalize("NFC", valor).strip()
        if not minimo <= len(texto) <= maximo:
            raise ValidationError(campo, f"Debe tener entre {minimo} y {maximo} caracteres")
        return texto

    @staticmethod
    def entero(valor, campo):
        if isinstance(valor, bool) or not re.fullmatch(r"[0-9]{1,10}", str(valor)):
            raise ValidationError(campo, "Seleccioná un identificador válido")
        numero = int(valor)
        if not 1 <= numero <= 2147483647:
            raise ValidationError(campo, "Seleccioná un identificador válido")
        return numero

    @staticmethod
    def decimal(valor, campo, minimo=0, maximo=MAX_IMPORTE):
        if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)) or len(str(valor)) > 64:
            raise ValidationError(campo, "Ingresá un número válido")
        try:
            numero = Decimal(str(valor))
        except InvalidOperation:
            raise ValidationError(campo, "Ingresá un número válido") from None
        if not numero.is_finite() or not Decimal(str(minimo)) <= numero <= maximo:
            raise ValidationError(campo, f"Debe estar entre {minimo} y {maximo}")
        if numero != numero.quantize(Decimal("0.01")):
            raise ValidationError(campo, "Se admiten como máximo dos decimales")
        return float(numero)

    @classmethod
    def documento(cls, valor):
        texto = cls.texto(valor, "dni", 7, 15)
        if not re.fullmatch(r"[0-9]{7,15}", texto):
            raise ValidationError("dni", "Ingresá de 7 a 15 dígitos, sin puntos ni guiones")
        return texto

    @classmethod
    def nombre(cls, valor):
        texto = cls.texto(valor, "nombre_completo", 3, 100)
        if sum(c.isalpha() for c in texto) < 2 or any(not (c.isalpha() or c in " '-.’") for c in texto):
            raise ValidationError("nombre_completo", "Ingresá un nombre con letras; se permiten espacios, apóstrofes, puntos y guiones")
        return texto

    @classmethod
    def telefono(cls, valor):
        texto = cls.texto(valor, "telefono", 6, 20)
        digitos = re.sub(r"[ ()+-]", "", texto)
        if not re.fullmatch(r"[0-9]{6,15}", digitos) or not re.fullmatch(r"\+?[0-9 ()-]+", texto):
            raise ValidationError("telefono", "Ingresá de 6 a 15 dígitos; el signo + solo puede ir al inicio")
        if texto.count("(") != texto.count(")") or texto.count("(") > 1 or ("(" in texto and texto.index("(") > texto.index(")")):
            raise ValidationError("telefono", "Revisá los paréntesis del teléfono")
        return texto

    @classmethod
    def email(cls, valor):
        if valor is None or valor == "":
            return None
        texto = cls.texto(valor, "email", 0, 100)
        if not texto:
            return None
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", texto):
            raise ValidationError("email", "Ingresá un correo electrónico válido")
        local = texto.split("@")[0]
        if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
            raise ValidationError("email", "Ingresá un correo electrónico válido")
        return texto
