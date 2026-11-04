"""Alta de administradores y ejemplos aditivos mediante autenticación administrativa."""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.controllers.auth_controller import AuthController
from app.controllers.usuario_controller import UsuarioController
from app.core.database import DatabaseManager
from app.services.datos_demostracion import DatosDemostracion
from app.models.usuario import Usuario
from app.utils.exceptions import DuplicateError, FormopackBaseError


class PrepararDemostracion:
    def ejecutar(self):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--cuenta", nargs=2, action="append", metavar=("NOMBRE", "CORREO"), default=[])
        parser.add_argument("--datos-demo", action="store_true", help="Agrega 14 envíos ficticios pendientes de cobro")
        args = parser.parse_args()
        if not args.cuenta and not args.datos_demo:
            parser.error("Indicá --cuenta o --datos-demo")
        email = input("Correo del administrador actual: ").strip()
        password = getpass.getpass("Contraseña actual de FormoPack: ")
        resultado = AuthController().login(email, password)
        if not resultado.success or resultado.usuario is None:
            raise ValueError("No se pudo verificar el ingreso")
        usuario = resultado.usuario
        if usuario.tipo_usuario != "administrador" or usuario.debe_cambiar_password:
            raise ValueError("Se requiere administrador con contraseña personal")
        if args.cuenta:
            provisoria = getpass.getpass("Contraseña provisoria para las cuentas nuevas: ")
            if provisoria != getpass.getpass("Repetí la contraseña provisoria: "):
                raise ValueError("Las contraseñas no coinciden")
            Usuario.validar_complejidad_password(provisoria)
            for nombre, correo in args.cuenta:
                try:
                    UsuarioController().crear_usuario(nombre, correo, "administrador", provisoria)
                    print(f"Cuenta creada con cambio obligatorio al ingresar: {correo}")
                except DuplicateError:
                    print(f"La cuenta ya existe, conserva sus datos y contraseña: {correo}")
        if args.datos_demo:
            guias = DatosDemostracion(DatabaseManager.get_instance()).cargar(usuario.id_usuario)
            print(f"Envíos ficticios nuevos, pendientes de cobro: {len(guias)}")
            for guia in guias:
                print(guia)


if __name__ == "__main__":
    try:
        PrepararDemostracion().ejecutar()
    except (FormopackBaseError, ValueError):
        print("No se completó la preparación. Revisá el acceso, los datos y la disponibilidad del sistema.")
        sys.exit(1)
