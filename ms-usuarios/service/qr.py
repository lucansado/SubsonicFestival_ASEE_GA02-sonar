# ms-usuarios/service/qr.py
# Código QR firmado con HMAC: SUBSONIC|<entrada_id>|<evento_id>|<firma>
# El staff puede comprobar la firma sin conexión si tiene el secreto.
import hashlib
import hmac
from config.settings import QR_SECRETO

PREFIJO = "SUBSONIC"


def _firma(entrada_id: str, evento_id: str) -> str:
    mensaje = f"{entrada_id}|{evento_id}".encode()
    return hmac.new(QR_SECRETO.encode(), mensaje, hashlib.sha256).hexdigest()[:32]


def generar(entrada_id: str, evento_id: str) -> str:
    return f"{PREFIJO}|{entrada_id}|{evento_id}|{_firma(entrada_id, evento_id)}"


def verificar(codigo_qr: str) -> tuple[str, str] | None:
    """Devuelve (entrada_id, evento_id) si la firma es válida; None si el QR es ilegible o falso."""
    partes = codigo_qr.split("|")
    if len(partes) != 4 or partes[0] != PREFIJO:
        return None
    _, entrada_id, evento_id, firma = partes
    if not hmac.compare_digest(firma, _firma(entrada_id, evento_id)):
        return None
    return entrada_id, evento_id
