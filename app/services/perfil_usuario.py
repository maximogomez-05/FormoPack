"""Edición de cuentas y fotografías verificadas del personal."""

import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError
from mysql.connector import IntegrityError

from app.core.database import DatabaseManager
from app.models.usuario import Usuario
from app.services.validacion_entrada import ValidacionEntrada as V
from app.utils.exceptions import AuthenticationError, DuplicateError, ValidationError


class PerfilUsuario:
    MAX_FOTO = 2 * 1024 * 1024

    def __init__(self, db=None):
        self.db = db or DatabaseManager.get_instance()

    def obtener(self, identificador):
        with self.db.cursor() as cur:
            cur.execute("""SELECT id_usuario, nombre, email, tipo_usuario, nro_licencia,
                EXISTS(SELECT 1 FROM fotos_perfil f WHERE f.id_usuario=usuarios.id_usuario) AS tiene_foto
                FROM usuarios WHERE id_usuario=%s""", (identificador,))
            fila = cur.fetchone()
        if not fila:
            raise ValidationError("usuario", "La cuenta no existe")
        return fila

    @staticmethod
    def _vigente(cur, identificador, version):
        cur.execute("SELECT * FROM usuarios WHERE id_usuario=%s FOR UPDATE", (identificador,))
        fila = cur.fetchone()
        if not fila or not fila["activo"] or fila["version_sesion"] != version:
            raise AuthenticationError("La sesión cambió. Volvé a ingresar.")
        return Usuario.from_db_row(fila)

    @staticmethod
    def _licencia(valor, rol):
        if rol != "chofer" or not valor.strip():
            return None
        licencia = V.texto(valor, "nro_licencia", 3, 50)
        if not re.fullmatch(r"[A-Za-z0-9 -]+", licencia):
            raise ValidationError("nro_licencia", "Usá letras, números, espacios o guiones")
        return licencia

    def guardar_datos(self, identificador, version, nombre, licencia=""):
        nombre = V.nombre(nombre)
        with self.db.cursor() as cur:
            usuario = self._vigente(cur, identificador, version)
            licencia = self._licencia(licencia, usuario.tipo_usuario)
            cur.execute("UPDATE usuarios SET nombre=%s, nro_licencia=%s WHERE id_usuario=%s",
                        (nombre, licencia, identificador))
        return nombre

    def cambiar_password(self, identificador, version, actual, nueva, confirmacion):
        if nueva != confirmacion:
            raise ValidationError("confirmacion", "Las contraseñas no coinciden")
        Usuario.validar_password_personal(nueva)
        with self.db.cursor() as cur:
            usuario = self._vigente(cur, identificador, version)
            if not usuario.verificar_password(actual):
                raise ValidationError("password_actual", "La contraseña actual es incorrecta")
            if usuario.verificar_password(nueva):
                raise ValidationError("password", "Elegí una contraseña diferente de la actual")
            cur.execute("""UPDATE usuarios SET credenciales_hash=%s, version_sesion=version_sesion+1
                WHERE id_usuario=%s""", (Usuario.hashear_password(nueva), identificador))
            cur.execute("UPDATE recuperacion_contrasenas SET utilizado=1 WHERE id_usuario=%s",
                        (identificador,))

    @classmethod
    def normalizar_foto(cls, archivo):
        datos = archivo.read(cls.MAX_FOTO + 1)
        if not datos or len(datos) > cls.MAX_FOTO:
            raise ValidationError("foto", "La foto debe pesar como máximo 2 MB")
        try:
            with Image.open(io.BytesIO(datos)) as imagen:
                if imagen.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("formato")
                if max(imagen.size) > 4096 or getattr(imagen, "is_animated", False):
                    raise ValueError("dimensiones")
                imagen.verify()
            with Image.open(io.BytesIO(datos)) as imagen:
                foto = ImageOps.exif_transpose(imagen).convert("RGB")
                foto = ImageOps.fit(foto, (256, 256), method=Image.Resampling.LANCZOS)
                salida = io.BytesIO()
                # Crear una imagen nueva elimina EXIF, GPS y otros metadatos.
                limpia = Image.new("RGB", foto.size)
                limpia.paste(foto)
                limpia.save(salida, format="PNG")
                return salida.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValidationError("foto", "Usá una imagen JPG, PNG o WebP estática de hasta 4096 × 4096 píxeles") from exc

    def guardar_foto(self, identificador, version, archivo):
        foto = self.normalizar_foto(archivo)
        with self.db.cursor() as cur:
            self._vigente(cur, identificador, version)
            cur.execute("""INSERT INTO fotos_perfil (id_usuario, imagen) VALUES (%s,%s)
                ON DUPLICATE KEY UPDATE imagen=VALUES(imagen)""", (identificador, foto))

    def quitar_foto(self, identificador, version):
        with self.db.cursor() as cur:
            self._vigente(cur, identificador, version)
            cur.execute("DELETE FROM fotos_perfil WHERE id_usuario=%s", (identificador,))

    def foto(self, identificador):
        with self.db.cursor() as cur:
            cur.execute("SELECT imagen FROM fotos_perfil WHERE id_usuario=%s", (identificador,))
            fila = cur.fetchone()
        return fila["imagen"] if fila else None

    def editar_cuenta(self, solicitante, version, identificador, nombre, email, licencia=""):
        nombre, email = V.nombre(nombre), V.email(email)
        if not email:
            raise ValidationError("email", "El correo es obligatorio")
        if solicitante == identificador:
            raise ValidationError("usuario", "Editá tus datos desde Mi perfil")
        try:
            with self.db.cursor() as cur:
                admin = self._vigente(cur, solicitante, version)
                if admin.tipo_usuario != "administrador":
                    raise AuthenticationError("No tenés permiso para editar cuentas")
                cur.execute("SELECT tipo_usuario FROM usuarios WHERE id_usuario=%s FOR UPDATE", (identificador,))
                cuenta = cur.fetchone()
                if not cuenta:
                    raise ValidationError("usuario", "La cuenta no existe")
                licencia = self._licencia(licencia, cuenta["tipo_usuario"])
                cur.execute("""UPDATE usuarios SET nombre=%s, email=%s, nro_licencia=%s,
                    version_sesion=version_sesion+1 WHERE id_usuario=%s""",
                            (nombre, email, licencia, identificador))
                cur.execute("UPDATE recuperacion_contrasenas SET utilizado=1 WHERE id_usuario=%s",
                            (identificador,))
        except IntegrityError as exc:
            if exc.errno == 1062:
                raise DuplicateError(entity="Usuario", identifier=email) from exc
            raise
