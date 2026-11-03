"""Almacenamiento privado de fotografías y lectura compatible de evidencias antiguas."""

import re
import uuid
from pathlib import Path


class AlmacenEvidencias:
    def __init__(self, privado, anterior=None):
        self.privado = Path(privado)
        self.anterior = Path(anterior) if anterior else None

    @staticmethod
    def _nombre(clave):
        if not isinstance(clave, str) or not re.fullmatch(r"uploads/pod/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", clave):
            raise FileNotFoundError("Evidencia no disponible")
        return clave.rsplit("/", 1)[1]

    @staticmethod
    def _ruta(carpeta, nombre):
        raiz = carpeta.resolve()
        ruta = (raiz / nombre).resolve()
        if not ruta.is_relative_to(raiz):
            raise FileNotFoundError("Evidencia no disponible")
        return ruta

    def guardar(self, envio_id, extension, contenido):
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Formato de evidencia inválido")
        self.privado.mkdir(parents=True, exist_ok=True, mode=0o700)
        nombre = f"pod_{int(envio_id)}_{uuid.uuid4().hex}{extension}"
        ruta = self._ruta(self.privado, nombre)
        with ruta.open("xb") as archivo:
            ruta.chmod(0o600)
            archivo.write(contenido)
        # Clave lógica conservada para compatibilidad con la base y el modo offline.
        return "uploads/pod/" + nombre

    def localizar(self, clave):
        nombre = self._nombre(clave)
        for carpeta in (self.privado, self.anterior):
            if carpeta is not None:
                ruta = self._ruta(carpeta, nombre)
                if ruta.is_file():
                    return ruta
        raise FileNotFoundError("Evidencia no disponible")

    def eliminar_temporal(self, clave):
        self._ruta(self.privado, self._nombre(clave)).unlink(missing_ok=True)
