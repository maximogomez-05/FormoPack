"""
Script de inicio del servidor web FormoPack Express.
Ejecutar con: py run.py
"""

import sys
import os

# Añadir raíz al path
ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

# Asegurar que existe la carpeta de sesiones Flask
session_dir = os.path.join(ROOT, ".flask_session")
os.makedirs(session_dir, exist_ok=True)

from web.app import create_app

if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 50)
    print("  [FormoPack Express] -- Servidor Web")
    print("=" * 50)
    print("  URL: http://localhost:5050")
    print("  Admin:      admin@formopack.com / admin123")
    print("  Recepcion:  recepcion@formopack.com / recep456")
    print("  Chofer:     chofer@formopack.com / chofer789")
    print("=" * 50 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5050, use_reloader=True)
