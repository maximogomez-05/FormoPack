"""Jerarquía de excepciones del dominio."""


class FormopackBaseError(Exception):
    """Excepción base del sistema."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# --- Base de Datos ---

class DatabaseConnectionError(FormopackBaseError):
    """Error al conectar con MySQL."""
    def __init__(self, message: str = "No se pudo conectar a la base de datos."):
        super().__init__(message, code="DB_CONNECTION_ERROR")


class DatabaseQueryError(FormopackBaseError):
    """Error al ejecutar consulta SQL."""
    def __init__(self, message: str = "Error al ejecutar la consulta en la base de datos."):
        super().__init__(message, code="DB_QUERY_ERROR")


# --- Autenticación y Autorización ---

class AuthenticationError(FormopackBaseError):
    """Credenciales inválidas."""
    def __init__(self, message: str = "Credenciales invalidas."):
        super().__init__(message, code="AUTH_INVALID_CREDENTIALS")


class UserNotFoundError(FormopackBaseError):
    """Usuario no registrado."""
    def __init__(self, identifier: str = ""):
        msg = f"Usuario no encontrado: '{identifier}'." if identifier else "Usuario no encontrado."
        super().__init__(msg, code="AUTH_USER_NOT_FOUND")


class UserInactiveError(FormopackBaseError):
    """Cuenta de usuario inactiva."""
    def __init__(self, email: str = ""):
        msg = f"La cuenta del usuario '{email}' esta inactiva."
        super().__init__(msg, code="AUTH_USER_INACTIVE")


class UnauthorizedRoleError(FormopackBaseError):
    """Rol sin permisos para la acción."""
    def __init__(self, role: str = "", action: str = ""):
        msg = f"El rol '{role}' no tiene permiso para: '{action}'."
        super().__init__(msg, code="AUTH_UNAUTHORIZED_ROLE")


# --- Validación ---

class ValidationError(FormopackBaseError):
    """Datos de entrada inválidos."""
    def __init__(self, field: str = "", reason: str = ""):
        msg = f"Validacion fallida en '{field}': {reason}." if field else "Error de validacion."
        super().__init__(msg, code="VALIDATION_ERROR")


# --- Dominio de Negocio (Sprint 2) ---

class ClienteNotFoundError(FormopackBaseError):
    """Cliente no encontrado por DNI."""
    def __init__(self, identifier: str = ""):
        msg = f"Cliente no encontrado: '{identifier}'." if identifier else "Cliente no encontrado."
        super().__init__(msg, code="CLIENTE_NOT_FOUND")


class EnvioNotFoundError(FormopackBaseError):
    """Envío no encontrado por número de guía."""
    def __init__(self, nro_guia: str = ""):
        msg = f"Envio no encontrado con guia: '{nro_guia}'." if nro_guia else "Envio no encontrado."
        super().__init__(msg, code="ENVIO_NOT_FOUND")


class TurnoCajaError(FormopackBaseError):
    """Error en operaciones de turno de caja."""
    def __init__(self, message: str = "Error en la operacion de caja."):
        super().__init__(message, code="TURNO_CAJA_ERROR")


class CotizacionError(FormopackBaseError):
    """Error en el cálculo de tarifa o cotización."""
    def __init__(self, message: str = "Error al calcular la cotizacion."):
        super().__init__(message, code="COTIZACION_ERROR")


class DuplicateError(FormopackBaseError):
    """Registro duplicado (DNI, número de guía, etc.)."""
    def __init__(self, entity: str = "", identifier: str = ""):
        msg = f"{entity} duplicado: '{identifier}'." if entity else "Registro duplicado."
        super().__init__(msg, code="DUPLICATE_ERROR")
