"""Validación del contenido que respalda una visita de reparto."""
import base64
import math
from io import BytesIO

from PIL import Image, ImageOps

from app.utils.exceptions import ValidationError


class EvidenciaEntrega:
    FORMATOS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}

    @staticmethod
    def imagen(stream, formato, limite_pixeles):
        try:
            with Image.open(stream, formats=[formato]) as original:
                if original.width * original.height > limite_pixeles or getattr(original, "n_frames", 1) != 1:
                    raise ValueError
                original.verify()
            stream.seek(0)
            with Image.open(stream, formats=[formato]) as original:
                original.load()
                return ImageOps.exif_transpose(original).convert("RGBA" if formato == "PNG" else "RGB")
        except (ValueError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValidationError("evidencia", "Imagen dañada, demasiado grande o de formato incorrecto") from exc

    @classmethod
    def firma(cls, valor):
        prefijo = "data:image/png;base64,"
        if not isinstance(valor, str) or not valor.startswith(prefijo) or len(valor) > 65535:
            raise ValidationError("firma", "Volvé a dibujar la firma en pantalla")
        try:
            contenido = base64.b64decode(valor[len(prefijo):], validate=True)
        except ValueError as exc:
            raise ValidationError("firma", "La firma está dañada") from exc
        imagen = cls.imagen(BytesIO(contenido), "PNG", 1024 * 1024)
        fondo = Image.new("RGBA", imagen.size, "white")
        fondo.alpha_composite(imagen)
        gris = fondo.convert("L")
        minimo, maximo = gris.getextrema()
        if maximo - minimo < 32:
            raise ValidationError("firma", "La firma debe contener un trazo visible")
        salida = BytesIO()
        gris.save(salida, format="PNG")
        firma = prefijo + base64.b64encode(salida.getvalue()).decode("ascii")
        if len(firma) > 65535:
            raise ValidationError("firma", "Volvé a dibujar una firma más simple")
        return firma

    @classmethod
    def foto(cls, stream, extension):
        formato = cls.FORMATOS[extension]
        imagen = cls.imagen(stream, formato, 20_000_000)
        salida = BytesIO()
        imagen.info.clear()
        imagen.save(salida, format=formato)
        return salida.getvalue()

    @staticmethod
    def gps(valor):
        if valor is None:
            return None
        try:
            lat, lon = map(float, valor.split(","))
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise ValidationError("gps", "Coordenadas fuera de rango o inválidas") from exc
        return f"{lat:.7f},{lon:.7f}"
