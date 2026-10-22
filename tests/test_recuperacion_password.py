"""Pruebas unitarias e integrales para el flujo de Recuperación de Contraseña."""

import pytest
from app.controllers.auth_controller import AuthController
from app.core.database import DatabaseManager
from app.utils.exceptions import ValidationError, UserInactiveError
from web.app import create_app


@pytest.fixture
def auth_ctrl():
    return AuthController()


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def test_solicitar_recuperacion_correo_inexistente(auth_ctrl):
    """Valida que rechace correos que no coinciden con ningún usuario registrado."""
    with pytest.raises(ValidationError) as excinfo:
        auth_ctrl.solicitar_recuperacion("desconocido_123456@formopack.com")
    assert "no coincide" in str(excinfo.value.message).lower()


def test_solicitar_recuperacion_correo_formato_invalido(auth_ctrl):
    """Valida rechazo de correos vacíos o con formato inválido."""
    with pytest.raises(ValidationError):
        auth_ctrl.solicitar_recuperacion("")

    with pytest.raises(ValidationError):
        auth_ctrl.solicitar_recuperacion("correo_sin_arroba")


def test_solicitar_recuperacion_exitoso_genera_codigo(auth_ctrl):
    """Valida que un usuario existente genere un código de 6 dígitos activo en la BD."""
    email = "admin@formopack.com"
    fila, codigo = auth_ctrl.solicitar_recuperacion(email)

    assert fila["email"] == email
    assert len(codigo) == 6
    assert codigo.isdigit()

    db = DatabaseManager.get_instance()
    with db.cursor(dictionary=True) as cur:
        cur.execute(
            """
            SELECT codigo, utilizado, expira_en 
            FROM recuperacion_contrasenas 
            WHERE id_usuario = %s AND utilizado = 0 
            ORDER BY creado_en DESC LIMIT 1
            """,
            (fila["id_usuario"],),
        )
        rec = cur.fetchone()
        assert rec is not None
        assert rec["codigo"] == codigo
        assert rec["utilizado"] == 0


def test_solicitar_recuperacion_invalida_codigos_anteriores(auth_ctrl):
    """Valida que al solicitar un nuevo código, los códigos previos queden invalidados."""
    email = "admin@formopack.com"
    fila_1, codigo_1 = auth_ctrl.solicitar_recuperacion(email)
    fila_2, codigo_2 = auth_ctrl.solicitar_recuperacion(email)

    assert fila_1["id_usuario"] == fila_2["id_usuario"]
    assert codigo_1 != codigo_2

    db = DatabaseManager.get_instance()
    with db.cursor(dictionary=True) as cur:
        cur.execute(
            "SELECT utilizado FROM recuperacion_contrasenas WHERE id_usuario = %s AND codigo = %s",
            (fila_1["id_usuario"], codigo_1),
        )
        anterior = cur.fetchone()
        assert anterior["utilizado"] == 1


def test_restablecer_password_codigo_incorrecto(auth_ctrl):
    """Valida que rechace un código de verificación erróneo."""
    email = "admin@formopack.com"
    auth_ctrl.solicitar_recuperacion(email)

    with pytest.raises(ValidationError) as excinfo:
        auth_ctrl.restablecer_password(
            email=email,
            codigo="000000",
            nueva_password="NuevaClave123!",
            confirmar_password="NuevaClave123!",
        )
    assert "incorrecto" in str(excinfo.value.message).lower()


def test_restablecer_password_discrepancia_confirmacion(auth_ctrl):
    """Valida que rechace si las contraseñas no coinciden."""
    email = "admin@formopack.com"
    _, codigo = auth_ctrl.solicitar_recuperacion(email)

    with pytest.raises(ValidationError) as excinfo:
        auth_ctrl.restablecer_password(
            email=email,
            codigo=codigo,
            nueva_password="NuevaClave123!",
            confirmar_password="OtraClaveDistinta456!",
        )
    assert "no coinciden" in str(excinfo.value.message).lower()


def test_restablecer_password_complejidad_invalida(auth_ctrl):
    """Valida que rechace claves que no cumplen longitud o caracteres requeridos."""
    email = "admin@formopack.com"
    _, codigo = auth_ctrl.solicitar_recuperacion(email)

    # Menos de 8 caracteres
    with pytest.raises(ValidationError):
        auth_ctrl.restablecer_password(email, codigo, "C1!", "C1!")

    # Solo letras
    with pytest.raises(ValidationError):
        auth_ctrl.restablecer_password(email, codigo, "Sololetraspass", "Sololetraspass")

    # Solo números
    with pytest.raises(ValidationError):
        auth_ctrl.restablecer_password(email, codigo, "123456789", "123456789")


def test_flujo_completo_restablecer_y_login(auth_ctrl):
    """Valida el ciclo completo: solicitar código -> cambiar contraseña -> login con nueva clave -> restaurar original."""
    email = "admin@formopack.com"
    clave_original = "admin123"
    clave_nueva = "TemporalPass2026!"

    # 1. Solicitar código
    fila, codigo = auth_ctrl.solicitar_recuperacion(email)

    # 2. Restablecer contraseña
    resultado = auth_ctrl.restablecer_password(
        email=email,
        codigo=codigo,
        nueva_password=clave_nueva,
        confirmar_password=clave_nueva,
    )
    assert resultado is True

    # 3. Validar que el código ya no puede volver a usarse
    with pytest.raises(ValidationError):
        auth_ctrl.restablecer_password(
            email=email,
            codigo=codigo,
            nueva_password=clave_nueva,
            confirmar_password=clave_nueva,
        )

    # 4. Validar login con la nueva clave
    login_res = auth_ctrl.login(email, clave_nueva)
    assert login_res.success is True
    assert login_res.usuario.email == email

    # 5. Restaurar la contraseña original para preservar el estado del entorno de pruebas
    auth_ctrl.solicitar_recuperacion(email)
    db = DatabaseManager.get_instance()
    with db.cursor(dictionary=True) as cur:
        cur.execute(
            "SELECT codigo FROM recuperacion_contrasenas WHERE id_usuario = %s AND utilizado = 0 ORDER BY creado_en DESC LIMIT 1",
            (fila["id_usuario"],),
        )
        cod_restaurar = cur.fetchone()["codigo"]
    auth_ctrl.restablecer_password(email, cod_restaurar, clave_original, clave_original)


def test_rutas_http_recuperacion(client):
    """Valida las rutas web de recuperar y restablecer contraseña."""
    # GET /recuperar-password
    res_get_rec = client.get("/recuperar-password")
    assert res_get_rec.status_code == 200
    assert b"Recuperar" in res_get_rec.data

    # GET /restablecer-password
    res_get_rest = client.get("/restablecer-password")
    assert res_get_rest.status_code == 200
    assert b"Restablecer" in res_get_rest.data

    # POST /recuperar-password con email inexistente
    res_post_inex = client.post("/recuperar-password", data={"email": "nadie_existe_aqui@formopack.com"}, follow_redirects=True)
    assert res_post_inex.status_code == 200
    assert "no coincide" in res_post_inex.get_data(as_text=True).lower()

    # POST /recuperar-password con email institucional válido
    res_post_ok = client.post("/recuperar-password", data={"email": "admin@formopack.com"}, follow_redirects=False)
    assert res_post_ok.status_code == 302
    assert "/restablecer-password" in res_post_ok.headers["Location"]
