# ms-usuarios/config/settings.py
# Configuración del servicio leída de variables de entorno (.env en local, docker-compose en contenedor)
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

NOMBRE_SERVICIO = "ms-usuarios"
PREFIJO_API = "/api/v1"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://usuarios:usuarios@localhost:5433/usuarios_db",
)
PUERTO = int(os.getenv("PUERTO", "8003"))

# Otros microservicios
ESPACIOS_URL = os.getenv("ESPACIOS_URL", "http://localhost:8002")
ESCALETA_URL = os.getenv("ESCALETA_URL", "http://localhost:8001")
TOKEN_SERVICIO = os.getenv("TOKEN_SERVICIO", "token-servicio-dev")
TIMEOUT_SEGUNDOS = float(os.getenv("TIMEOUT_SEGUNDOS", "2"))
REINTENTOS = int(os.getenv("REINTENTOS", "3"))

# Firma HMAC de los códigos QR (en producción, un secreto largo en el gestor de configuración)
QR_SECRETO = os.getenv("QR_SECRETO", "secreto-qr-dev")

# Ruta al JSON de la cuenta de servicio de Firebase. Vacío = Firebase simulado (solo log)
FIREBASE_CREDENCIALES = os.getenv("FIREBASE_CREDENCIALES", "")
