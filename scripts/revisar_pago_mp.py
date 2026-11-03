"""Conciliación administrativa de un pago antiguo sin metadata ni preferencia original.

No crea cobros externos. Autentica al administrador, muestra los datos y pide
confirmación antes de registrar el pago existente y su auditoría.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.controllers.auth_controller import AuthController
from app.services.conciliacion_mp import ConciliacionMP
from app.utils.exceptions import FormopackBaseError


class RevisionPagoCLI:
    def ejecutar(self, argumentos=None):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--guia", required=True)
        parser.add_argument("--pago", required=True)
        args = parser.parse_args(argumentos)
        correo = input("Correo del administrador de FormoPack: ").strip()
        clave = getpass.getpass("Contraseña de FormoPack (no la del VPS): ")
        actor = AuthController().login(correo, clave).usuario
        if actor.tipo_usuario != "administrador" or actor.debe_cambiar_password:
            raise ValueError("Se requiere administrador con contraseña definitiva.")
        servicio = ConciliacionMP()
        datos = servicio.previsualizar_revision_legacy(args.pago, args.guia, actor.id_usuario)
        for campo, valor in datos.items():
            print(f"{campo}: {valor}")
        print("Se registrará el pago existente. No se moverá dinero en Mercado Pago.")
        motivo = input("Motivo de la revisión (20 a 500 caracteres): ").strip()
        if input("Para conciliar este pago, escribí CONFIRMAR: ").strip() != "CONFIRMAR":
            print("Cancelado. No se registró ningún pago.")
            return
        resultado = servicio.conciliar_revision_legacy(args.pago, args.guia, actor.id_usuario, motivo)
        print("Resultado:", resultado)


if __name__ == "__main__":
    try:
        RevisionPagoCLI().ejecutar()
    except (FormopackBaseError, ValueError, EOFError, KeyboardInterrupt) as error:
        print("Revisión detenida:", error, file=sys.stderr)
        sys.exit(1)
