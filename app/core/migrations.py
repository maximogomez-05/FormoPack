"""Sistema formal de migraciones numeradas para FormoPack Express."""

import logging
from pathlib import Path
from typing import List, Tuple
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "migrations"


class MigrationManager:
    """Gestiona el control de versiones y aplicación de migraciones de la base de datos."""

    def __init__(self, db_manager: DatabaseManager = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def inicializar_tabla_migraciones(self) -> None:
        """Crea la tabla de control de migraciones si no existe."""
        with self.db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(100) PRIMARY KEY,
                    aplicado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

    def obtener_migraciones_aplicadas(self) -> set[str]:
        """Devuelve el conjunto de nombres de migraciones ya aplicadas."""
        self.inicializar_tabla_migraciones()
        with self.db.cursor(dictionary=True) as cur:
            cur.execute("SELECT version FROM schema_migrations")
            filas = cur.fetchall()
            return {f["version"] for f in filas}

    def obtener_archivos_migracion(self) -> List[Path]:
        """Obtiene todos los archivos SQL en el directorio de migraciones ordenados por nombre."""
        if not MIGRATIONS_DIR.exists():
            return []
        archivos = [p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file()]
        return sorted(archivos, key=lambda p: p.name)

    def aplicar_migraciones(self, desde: str | None = None) -> List[Tuple[str, bool]]:
        """Aplica todas las migraciones pendientes en orden correlativo."""
        if desde is not None and (not desde.isdigit() or len(desde) != 3):
            raise ValueError("La versión inicial debe tener tres dígitos")
        self.inicializar_tabla_migraciones()
        aplicadas = self.obtener_migraciones_aplicadas()
        archivos = self.obtener_archivos_migracion()
        if desde is not None:
            archivos = [archivo for archivo in archivos if archivo.name[:3] >= desde]
        resultados = []

        conn = self.db.get_connection()
        cur = None
        try:
            cur = conn.cursor()
            for archivo in archivos:
                version = archivo.stem
                if version in aplicadas:
                    resultados.append((version, False))
                    continue

                logger.info("Aplicando migración: %s...", version)
                contenido = archivo.read_text(encoding="utf-8")
                # Dividir sentencias respetando delimitadores básicos
                sentencias = [s.strip() for s in contenido.split(";") if s.strip()]
                for sentencia in sentencias:
                    cur.execute(sentencia)

                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                conn.commit()
                logger.info("Migración %s aplicada exitosamente.", version)
                resultados.append((version, True))
        except Exception as e:
            conn.rollback()
            logger.error("Error al aplicar migración: %s", e)
            raise
        finally:
            if cur:
                cur.close()
            conn.close()

        return resultados


def ejecutar_migraciones(desde: str | None = None) -> None:
    """Función de utilidad para ejecutar migraciones desde CLI o scripts."""
    manager = MigrationManager()
    resultados = manager.aplicar_migraciones(desde=desde)
    print("=" * 50)
    print("  [FormoPack] Estado de Migraciones de Base de Datos")
    print("=" * 50)
    for version, recien_aplicada in resultados:
        estado = "APLICADA AHORA" if recien_aplicada else "YA APLICADA"
        print(f"  [{estado}] {version}")
    print("=" * 50)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migraciones de FormoPack")
    parser.add_argument("--desde", help="Versión inicial, por ejemplo 005 para una instalación existente")
    ejecutar_migraciones(desde=parser.parse_args().desde)
