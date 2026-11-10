"""Procesador operativo para systemd. --resumen consulta sin enviar correos."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import DatabaseManager
from app.services.cola_notificaciones import ColaNotificaciones
from config.settings import EmailConfig


class ProcesadorNotificaciones:
    def ejecutar(self):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--limite", type=int, default=10, choices=range(1, 101), metavar="1..100")
        parser.add_argument("--resumen", action="store_true")
        args = parser.parse_args()
        db = DatabaseManager.get_instance()
        if args.resumen:
            with db.cursor() as cur:
                cur.execute("SELECT estado,COUNT(*) AS cantidad FROM notificaciones_operativas GROUP BY estado")
                for fila in cur.fetchall():
                    print(f"{fila['estado']}: {fila['cantidad']}")
            return
        if not EmailConfig.USER or not EmailConfig.PASSWORD:
            raise SystemExit("SMTP no configurado. Los avisos permanecen pendientes.")
        enviados = ColaNotificaciones(db).procesar(args.limite)
        print(f"Avisos enviados: {enviados}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ProcesadorNotificaciones().ejecutar()
