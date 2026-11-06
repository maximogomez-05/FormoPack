import io
from time import time

import pytest
from PIL import Image

from app.services.perfil_usuario import PerfilUsuario
from app.utils.exceptions import ValidationError
from tests.test_regresion_paginas import aplicacion, db


def foto_png():
    salida = io.BytesIO()
    imagen = Image.new("RGB", (32, 48), "blue")
    exif = Image.Exif()
    exif[270] = "Información privada"
    imagen.save(salida, "PNG", exif=exif)
    return salida.getvalue()


def cliente(app, identificador=1):
    app.config["WTF_CSRF_ENABLED"] = False
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(usuario_id=identificador, version_sesion=0, inicio_sesion=time(), ultima_actividad=time())
    return c


@pytest.mark.parametrize("identificador", [1, 2, 3])
def test_edicion_propia_ignora_id_y_rol_del_formulario(aplicacion, db, identificador):
    c = cliente(aplicacion, identificador)
    assert c.get("/perfil/").status_code == 200
    respuesta = c.post("/perfil/", data={"nombre": "Persona Actualizada", "nro_licencia": "LI-999",
                                        "id_usuario": "999", "tipo_usuario": "administrador"})
    assert respuesta.status_code == 302
    with db.cursor() as cur:
        cur.execute("SELECT nombre,tipo_usuario,nro_licencia FROM usuarios WHERE id_usuario=%s", (identificador,))
        fila = cur.fetchone()
        assert fila["nombre"] == "Persona Actualizada"
        assert fila["tipo_usuario"] == {1: "administrador", 2: "recepcionista", 3: "chofer"}[identificador]
        assert fila["nro_licencia"] == ("LI-999" if identificador == 3 else None)
    assert "Persona Actualizada" in c.get("/perfil/").get_data(as_text=True)


def test_foto_privada_reemplazar_y_quitar(aplicacion):
    c = cliente(aplicacion)
    assert c.post("/perfil/foto", data={"foto": (io.BytesIO(foto_png()), "foto.png")}).status_code == 302
    respuesta = c.get("/perfil/foto")
    assert respuesta.mimetype == "image/png"
    imagen = Image.open(io.BytesIO(respuesta.data))
    assert imagen.size == (256, 256) and not imagen.getexif()
    assert "no-store" in respuesta.headers["Cache-Control"]
    assert aplicacion.test_client().get("/perfil/foto").status_code == 302
    otro = cliente(aplicacion, 2)
    assert otro.get("/perfil/foto?id_usuario=1").mimetype == "image/svg+xml"
    assert c.post("/perfil/foto", data={"foto": (io.BytesIO(b"<script>mal</script>"), "foto.png")}).status_code == 400
    assert c.get("/perfil/foto").data == respuesta.data
    assert c.post("/perfil/foto", data={"quitar": "1"}).status_code == 302
    assert c.get("/perfil/foto").mimetype == "image/svg+xml"


@pytest.mark.parametrize("contenido", [b"", b"x" * (2 * 1024 * 1024 + 1),
                                      b'<svg xmlns="http://www.w3.org/2000/svg"/>'],
                         ids=["vacio", "exceso", "svg"])
def test_rechaza_archivos_invalidos(contenido):
    with pytest.raises(ValidationError):
        PerfilUsuario.normalizar_foto(io.BytesIO(contenido))


def test_password_incorrecta_no_cambia_y_nueva_revoca_sesion(aplicacion, db):
    c = cliente(aplicacion)
    with db.cursor() as cur:
        cur.execute("SELECT credenciales_hash FROM usuarios WHERE id_usuario=1")
        anterior = cur.fetchone()["credenciales_hash"]
    assert c.post("/perfil/password", data={"password_actual": "incorrecta", "password": "NuevaClave123",
                                            "confirmacion": "NuevaClave123"}).status_code == 400
    with db.cursor() as cur:
        cur.execute("SELECT credenciales_hash FROM usuarios WHERE id_usuario=1")
        assert cur.fetchone()["credenciales_hash"] == anterior
    assert c.post("/perfil/password", data={"password_actual": "admin123", "password": "NuevaClave123",
                                            "confirmacion": "NuevaClave123"}).status_code == 302
    assert c.get("/sesion", headers={"Accept": "application/json"}).status_code == 401
    from app.controllers.auth_controller import AuthController
    assert AuthController(db).login("admin@formopack.com", "NuevaClave123").success


def test_perfiles_ajenos_protegidos_incluso_del_administrador(aplicacion, db):
    c = cliente(aplicacion)
    for metodo in (c.get, c.post):
        assert metodo("/perfil/cuentas/2").status_code == 403
    from app.utils.exceptions import AuthenticationError
    with pytest.raises(AuthenticationError):
        PerfilUsuario(db).editar_cuenta(1, 0, 2, "Nombre Nuevo", "nuevo@example.com")
    with db.cursor() as cur:
        cur.execute("SELECT email FROM usuarios WHERE id_usuario=2")
        assert cur.fetchone()["email"] == "recepcion@formopack.com"


def test_csrf_y_nombre_invalido(aplicacion):
    c = cliente(aplicacion)
    assert c.post("/perfil/", data={"nombre": "12345"}).status_code == 400
    aplicacion.config["WTF_CSRF_ENABLED"] = True
    assert c.post("/perfil/", data={"nombre": "Nombre Nuevo"}).status_code == 400
    assert c.post("/perfil/foto", data={"quitar": "1"}).status_code == 400


def test_migracion_repetida_conserva_foto(aplicacion, db):
    from app.core.migrations import MigrationManager
    servicio = PerfilUsuario(db)
    servicio.guardar_foto(1, 0, io.BytesIO(foto_png()))
    anterior = servicio.foto(1)
    MigrationManager(db).aplicar_migraciones(desde="013")
    MigrationManager(db).aplicar_migraciones(desde="013")
    assert servicio.foto(1) == anterior
