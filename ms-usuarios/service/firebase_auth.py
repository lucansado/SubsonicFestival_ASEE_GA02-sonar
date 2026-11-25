# ms-usuarios/service/firebase_auth.py
# Integración con Firebase Authentication: custom claim "rol" y borrado de cuentas.
# Si FIREBASE_CREDENCIALES está vacío (desarrollo y tests) las operaciones solo se registran en el log.
import logging
import threading
from config.settings import FIREBASE_CREDENCIALES

log = logging.getLogger("firebase")
_app = None
_lock = threading.Lock()


def _firebase():
    global _app
    if not FIREBASE_CREDENCIALES:
        return None
    if _app is None:
        import firebase_admin
        from firebase_admin import credentials
        with _lock:
            if _app is None:
                _app = firebase_admin.initialize_app(
                    credentials.Certificate(FIREBASE_CREDENCIALES), name="ms-usuarios")
    return _app


def inicializar() -> None:
    """Una ruta configurada incorrectamente debe fallar al arrancar, nunca simular Firebase."""
    _firebase()


def asignar_rol(uid: str, rol: str) -> None:
    """El gateway lee el rol del claim del token (tras renovar el token en el front-end)."""
    app = _firebase()
    if app is None:
        log.info("[Firebase simulado] claim rol=%s para %s", rol, uid)
        return
    from firebase_admin import auth
    # set_custom_user_claims reemplaza el mapa entero: conservar los otros claims.
    claims = dict(auth.get_user(uid, app=app).custom_claims or {})
    claims["rol"] = rol
    auth.set_custom_user_claims(uid, claims, app=app)


def eliminar_cuenta(uid: str) -> None:
    app = _firebase()
    if app is None:
        log.info("[Firebase simulado] cuenta %s eliminada", uid)
        return
    from firebase_admin import auth
    try:
        auth.delete_user(uid, app=app)
    except auth.UserNotFoundError:
        pass
