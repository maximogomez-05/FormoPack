import base64
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.services.evidencia_entrega import EvidenciaEntrega
from app.utils.exceptions import ValidationError


def png(trazo=True):
    imagen = Image.new("RGBA", (40, 20))
    if trazo:
        ImageDraw.Draw(imagen).line((2, 3, 24, 15), fill="black", width=2)
    salida = BytesIO()
    imagen.save(salida, format="PNG")
    return salida.getvalue()


def firma_prueba(trazo=True):
    return "data:image/png;base64," + base64.b64encode(png(trazo)).decode("ascii")


def test_firma_valida_y_lienzo_vacio():
    assert EvidenciaEntrega.firma(firma_prueba()).startswith("data:image/png;base64,")
    with pytest.raises(ValidationError):
        EvidenciaEntrega.firma(firma_prueba(False))


@pytest.mark.parametrize("valor", ["data:image/png;base64,YQ==", "data:image/png;base64,!", "data:image/svg+xml;base64,YQ=="])
def test_firma_invalida(valor):
    with pytest.raises(ValidationError):
        EvidenciaEntrega.firma(valor)


def test_foto_decodifica_y_descarta_adjunto():
    datos = png()
    assert b"extra-privado" not in EvidenciaEntrega.foto(BytesIO(datos + b"extra-privado"), ".png")
    for contenido, extension in [(datos[:18], ".png"), (datos, ".jpg")]:
        with pytest.raises(ValidationError):
            EvidenciaEntrega.foto(BytesIO(contenido), extension)


@pytest.mark.parametrize("valor", ["NaN,0", "0,inf", "-91,0", "0,181", "x", "1,2,3"])
def test_gps_invalido(valor):
    with pytest.raises(ValidationError):
        EvidenciaEntrega.gps(valor)
