"""Prueba explícita contra Firebase real con una cuenta temporal creada por este script."""
import argparse
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from firebase_admin import auth  # noqa: E402
from service.firebase_auth import _firebase  # noqa: E402


def comprobar(api_url: str) -> None:
    app = _firebase()
    if app is None:
        raise SystemExit("Configura FIREBASE_CREDENCIALES; esta prueba no admite el modo simulado.")
    uid = f"prueba-usuarios-{uuid4().hex}"
    email = f"{uid}@example.invalid"
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=15,
                      headers={"X-User-Id": uid, "X-User-Email": email}) as cliente:
        # Si la creación falla, no se intenta borrar ningún UID que pudiera ser ajeno.
        auth.create_user(uid=uid, email=email, disabled=True, app=app)
        eliminado = False
        try:
            respuesta = cliente.post("/api/v1/usuarios", json={"nombre": "Prueba temporal", "rol": "CLIENTE"})
            respuesta.raise_for_status()
            claims = auth.get_user(uid, app=app).custom_claims or {}
            if claims.get("rol") != "CLIENTE":
                raise RuntimeError("El registro no asignó el claim rol=CLIENTE en Firebase")
            print("[OK] Registro y claim rol=CLIENTE en Firebase")
            cliente.delete("/api/v1/usuarios/me").raise_for_status()
            try:
                auth.get_user(uid, app=app)
            except auth.UserNotFoundError:
                eliminado = True
                print("[OK] La API eliminó la cuenta en Firebase")
            else:
                raise RuntimeError("La API no eliminó la cuenta en Firebase")
        finally:
            if not eliminado:
                # También se intenta limpiar un perfil cuya alta pudo llegar a guardarse.
                try:
                    respuesta = cliente.delete("/api/v1/usuarios/me")
                    if respuesta.status_code != 404:
                        respuesta.raise_for_status()
                except httpx.HTTPError:
                    print(f"[AVISO] No se pudo limpiar el perfil temporal {uid} en la API", file=sys.stderr)
            try:
                auth.delete_user(uid, app=app)
            except auth.UserNotFoundError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8003")
    comprobar(parser.parse_args().api_url)
