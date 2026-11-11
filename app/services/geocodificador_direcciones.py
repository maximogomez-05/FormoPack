"""Autocompletado privado del servidor mediante Photon y datos de OpenStreetMap."""

from __future__ import annotations

import json
import os
import unicodedata
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config.settings import AppConfig
from app.services.geografia_destino import normalizar_nombre, punto_en_localidad
from app.utils.exceptions import ValidationError


class ErrorGeocodificacion(Exception):
    """El proveedor de geocodificación no respondió con datos utilizables."""


class GeocodificadorDirecciones:
    BASE_URL = os.getenv("FORMOPACK_GEOCODER_URL", "https://photon.komoot.io").rstrip("/")
    USER_AGENT = os.getenv("FORMOPACK_GEOCODER_USER_AGENT", "FormoPackExpress/1.0 (operaciones de logística)")
    TIMEOUT_SEGUNDOS = 5
    TIEMPO_TOKEN_SEGUNDOS = 7200

    @classmethod
    def firmar_sugerencia(cls, sugerencia: dict, id_localidad: int) -> str:
        serializador = URLSafeTimedSerializer(AppConfig.SECRET_KEY, salt="formopack-geocoded-address-v1")
        direccion = unicodedata.normalize("NFC", str(sugerencia["direccion"]).strip())
        return serializador.dumps({
            "direccion": direccion,
            "id_localidad": int(id_localidad),
            "latitud": float(f"{float(sugerencia['latitud']):.7f}"),
            "longitud": float(f"{float(sugerencia['longitud']):.7f}"),
        })

    @classmethod
    def validar_sugerencia(cls, token: str, direccion: str, id_localidad: int, latitud, longitud) -> None:
        serializador = URLSafeTimedSerializer(AppConfig.SECRET_KEY, salt="formopack-geocoded-address-v1")
        try:
            carga = serializador.loads(token or "", max_age=cls.TIEMPO_TOKEN_SEGUNDOS)
        except (BadSignature, SignatureExpired) as exc:
            raise ValidationError("direccion_destino", "Elegí nuevamente una dirección sugerida o marcá el mapa") from exc
        direccion_normalizada = unicodedata.normalize("NFC", str(direccion or "").strip())
        try:
            latitud = float(latitud)
            longitud = float(longitud)
        except (TypeError, ValueError) as exc:
            raise ValidationError("direccion_destino", "La dirección no tiene coordenadas válidas") from exc
        if (carga.get("direccion") != direccion_normalizada
            or carga.get("id_localidad") != int(id_localidad)
            or abs(carga.get("latitud", 999) - latitud) > 0.0000001
            or abs(carga.get("longitud", 999) - longitud) > 0.0000001):
            raise ValidationError("direccion_destino", "La dirección cambió. Volvé a seleccionarla en las sugerencias")

    @classmethod
    def sugerir(cls, texto: str, localidad: str) -> list[dict]:
        consulta = " ".join(str(texto or "").split())
        if len(consulta) < 3 or len(consulta) > 120:
            return []
        centro = cls._centro_para(localidad)
        datos = cls._consultar("/api/", {
            "q": f"{consulta}, {localidad}, Formosa, Argentina",
            "lat": centro[0], "lon": centro[1], "limit": 12,
        })
        return cls._filtrar(datos.get("features", []), localidad)

    @classmethod
    def inversa(cls, latitud: float, longitud: float, localidad: str) -> dict | None:
        cls._centro_para(localidad)
        if not punto_en_localidad(localidad, latitud, longitud):
            return None
        datos = cls._consultar("/reverse", {
            "lat": float(latitud), "lon": float(longitud), "limit": 1,
        })
        resultados = cls._filtrar(datos.get("features", []), localidad)
        return resultados[0] if resultados else None

    @staticmethod
    def _centro_para(localidad: str) -> tuple[float, float]:
        from app.services.geografia_destino import centro_localidad
        centro = centro_localidad(localidad)
        if centro is None:
            raise ValueError("La localidad no tiene un centro geográfico configurado")
        return centro

    @classmethod
    def _consultar(cls, ruta: str, parametros: dict) -> dict:
        url = f"{cls.BASE_URL}{ruta}?{urlencode(parametros)}"
        solicitud = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": cls.USER_AGENT,
        })
        try:
            with urlopen(solicitud, timeout=cls.TIMEOUT_SEGUNDOS) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            raise ErrorGeocodificacion("No se pudo consultar el servicio de direcciones") from exc
        if not isinstance(datos, dict):
            raise ErrorGeocodificacion("El servicio devolvió una respuesta inválida")
        return datos

    @classmethod
    def _filtrar(cls, caracteristicas: list, localidad: str) -> list[dict]:
        resultados = []
        localidad_normalizada = normalizar_nombre(localidad)
        alias_localidad = localidad_normalizada.removesuffix(" capital")
        for caracteristica in caracteristicas:
            propiedades = caracteristica.get("properties") or {}
            geometria = caracteristica.get("geometry") or {}
            coordenadas = geometria.get("coordinates") or []
            if len(coordenadas) < 2:
                continue
            longitud, latitud = coordenadas[:2]
            if str(propiedades.get("country") or "").lower() not in {"argentina", "argentine republic"}:
                continue
            if not punto_en_localidad(localidad, latitud, longitud):
                continue
            ciudad = propiedades.get("city") or propiedades.get("locality")
            if ciudad:
                ciudad_normalizada = normalizar_nombre(ciudad)
                if ciudad_normalizada not in {localidad_normalizada, alias_localidad}:
                    continue
            calle = str(propiedades.get("street") or propiedades.get("name") or "").strip()
            altura = str(propiedades.get("housenumber") or "").strip()
            if not calle:
                continue
            direccion = f"{calle} {altura}".strip()
            resultados.append({
                "direccion": direccion,
                "latitud": float(latitud),
                "longitud": float(longitud),
            })
            if len(resultados) == 6:
                break
        return resultados
