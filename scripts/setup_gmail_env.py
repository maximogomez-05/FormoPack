"""
Script para auto-generar la configuración de notificaciones por email en el archivo .env.
Utiliza la cuenta y contraseña de aplicación predefinidas del proyecto.
"""

import os
from pathlib import Path

def main():
    print("=" * 50)
    print(" Configuración Automática de Notificaciones (Gmail) ")
    print("=" * 50)

    # Credenciales predefinidas del proyecto
    gmail_user = "formopackucp@gmail.com"
    gmail_app_password = "rhetfnnnsdhwsynf"
    alertas_email = "formopackucp@gmail.com"  # Por defecto manda correos a la misma cuenta para pruebas
    gmail_host = "smtp.gmail.com"
    gmail_port = "465"
    
    # Encontrar la ruta del archivo .env (raíz del proyecto)
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"

    env_vars = {}
    
    # Conservar el archivo actual si existe
    if env_path.exists():
        print(f"Leyendo archivo existente en {env_path}...")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    else:
        print(f"Creando nuevo archivo .env en {env_path}...")

    # Actualizar o insertar las variables de Gmail
    env_vars["GMAIL_SMTP_HOST"] = gmail_host
    env_vars["GMAIL_SMTP_PORT"] = gmail_port
    env_vars["GMAIL_USER"] = gmail_user
    env_vars["GMAIL_APP_PASSWORD"] = gmail_app_password
    env_vars["ALERTAS_EMAIL"] = alertas_email

    print("\nEscribiendo credenciales...")

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# ==========================================\n")
            f.write("# Configuración Base del Sistema\n")
            f.write("# ==========================================\n")
            for key, value in env_vars.items():
                if not key.startswith("GMAIL_") and key != "ALERTAS_EMAIL":
                    f.write(f"{key}={value}\n")
            
            f.write("\n# ==========================================\n")
            f.write("# Configuración de Correo Electrónico (RF 5.4)\n")
            f.write("# ==========================================\n")
            f.write(f"GMAIL_SMTP_HOST={gmail_host}\n")
            f.write(f"GMAIL_SMTP_PORT={gmail_port}\n")
            f.write(f"GMAIL_USER={gmail_user}\n")
            f.write(f"GMAIL_APP_PASSWORD={gmail_app_password}\n")
            f.write(f"ALERTAS_EMAIL={alertas_email}\n")
                
        print(f"\n¡Éxito! Las credenciales predefinidas han sido configuradas correctamente en el archivo .env.")
        print(f"Cuenta de envío configurada: {gmail_user}")
    except Exception as e:
        print(f"\nOcurrió un error al intentar guardar el archivo .env: {e}")

if __name__ == "__main__":
    main()
