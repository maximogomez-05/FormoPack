"""Quita solo los tres avatares sintéticos de la carga integral de showcase.

Una foto subida posteriormente se conserva: se comparan todos sus píxeles con
el avatar original. Ejecutar desde la raíz: python scripts/limpiar_avatares_muestra.py
"""
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw


CUENTAS = {
    'lucia.molina@showcase.example': 'LM',
    'andres.cabrera@showcase.example': 'AC',
    'sergio.duarte@showcase.example': 'SD',
}


def es_avatar_muestra(contenido, iniciales):
    esperado = Image.new('RGB', (256, 256), '#e5edf5')
    ImageDraw.Draw(esperado).text((105, 115), iniciales, fill='#193655')
    try:
        with Image.open(BytesIO(contenido)) as actual:
            if actual.size != esperado.size:
                return False
            return ImageChops.difference(actual.convert('RGB'), esperado).getbbox() is None
    except (OSError, ValueError):
        return False


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.database import DatabaseManager
    eliminados = 0
    with DatabaseManager.get_instance().cursor() as cur:
        for email, iniciales in CUENTAS.items():
            cur.execute('''SELECT f.id_usuario,f.imagen FROM fotos_perfil f
                JOIN usuarios u ON u.id_usuario=f.id_usuario WHERE u.email=%s FOR UPDATE''', (email,))
            foto = cur.fetchone()
            if foto and es_avatar_muestra(foto['imagen'], iniciales):
                cur.execute('DELETE FROM fotos_perfil WHERE id_usuario=%s', (foto['id_usuario'],))
                eliminados += cur.rowcount
    print(f'Avatares sintéticos retirados: {eliminados}. Las otras fotos se conservaron.')


if __name__ == '__main__':
    main()
