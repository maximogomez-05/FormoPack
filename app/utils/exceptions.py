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
