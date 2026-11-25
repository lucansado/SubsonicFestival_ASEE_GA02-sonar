from types import SimpleNamespace
from unittest.mock import Mock

import firebase_admin
from firebase_admin import auth, credentials
import pytest
from config.seguridad import Identidad
from model.dto.usuario_dto import RegistroEntradaDTO
from model.models import Usuario
from service import firebase_auth, usuario_service


def test_inicializa_una_vez_con_la_ruta_configurada(monkeypatch):
    monkeypatch.setattr(firebase_auth, "FIREBASE_CREDENCIALES", "credenciales-de-prueba.json")
    monkeypatch.setattr(firebase_auth, "_app", None)
    certificado, app = object(), object()
    crear_certificado, iniciar = Mock(return_value=certificado), Mock(return_value=app)
    monkeypatch.setattr(credentials, "Certificate", crear_certificado)
    monkeypatch.setattr(firebase_admin, "initialize_app", iniciar)
    firebase_auth.inicializar()
    firebase_auth.inicializar()
    crear_certificado.assert_called_once_with("credenciales-de-prueba.json")
    iniciar.assert_called_once_with(certificado, name="ms-usuarios")


def test_ruta_incorrecta_no_activa_simulacion(monkeypatch, tmp_path):
    monkeypatch.setattr(firebase_auth, "FIREBASE_CREDENCIALES", str(tmp_path / "no-existe.json"))
    monkeypatch.setattr(firebase_auth, "_app", None)
    with pytest.raises(FileNotFoundError):
        firebase_auth.inicializar()


@pytest.mark.parametrize("claims", [None, {"otro_permiso": True, "rol": "CLIENTE"}])
def test_asigna_rol_sin_borrar_otros_claims(monkeypatch, claims):
    app = object()
    monkeypatch.setattr(firebase_auth, "_firebase", lambda: app)
    obtener = Mock(return_value=SimpleNamespace(custom_claims=claims))
    asignar = Mock()
    monkeypatch.setattr(auth, "get_user", obtener)
    monkeypatch.setattr(auth, "set_custom_user_claims", asignar)
    firebase_auth.asignar_rol("uid", "PROVEEDOR")
    obtener.assert_called_once_with("uid", app=app)
    asignar.assert_called_once_with("uid", dict(claims or {}) | {"rol": "PROVEEDOR"}, app=app)


def test_registro_y_borrado_invocan_sdk_desde_api(cliente_http, monkeypatch):
    app = object()
    monkeypatch.setattr(firebase_auth, "_firebase", lambda: app)
    monkeypatch.setattr(auth, "get_user", Mock(return_value=SimpleNamespace(custom_claims=None)))
    asignar, borrar = Mock(), Mock()
    monkeypatch.setattr(auth, "set_custom_user_claims", asignar)
    monkeypatch.setattr(auth, "delete_user", borrar)
    cabeceras = {"X-User-Id": "uid-prueba", "X-User-Email": "prueba@test.com"}
    respuesta = cliente_http.post("/api/v1/usuarios", headers=cabeceras,
                                  json={"nombre": "Prueba", "rol": "CLIENTE"})
    assert respuesta.status_code == 201
    asignar.assert_called_once_with("uid-prueba", {"rol": "CLIENTE"}, app=app)
    assert cliente_http.delete("/api/v1/usuarios/me", headers=cabeceras).status_code == 204
    borrar.assert_called_once_with("uid-prueba", app=app)


def test_borrado_idempotente_si_ya_no_existe_en_firebase(monkeypatch):
    monkeypatch.setattr(firebase_auth, "_firebase", lambda: object())
    monkeypatch.setattr(auth, "delete_user", Mock(side_effect=auth.UserNotFoundError("no existe")))
    firebase_auth.eliminar_cuenta("uid")


def test_fallo_claim_no_deja_perfil_irrecuperable(db, monkeypatch):
    asignar = Mock(side_effect=RuntimeError("Firebase no responde"))
    monkeypatch.setattr(firebase_auth, "asignar_rol", asignar)
    identidad = Identidad(id="uid", email="uid@test.com")
    datos = RegistroEntradaDTO(nombre="Prueba", rol="CLIENTE")
    with pytest.raises(RuntimeError):
        usuario_service.registrar(db, identidad, datos)
    assert db.get(Usuario, "uid") is None
    asignar.side_effect = None
    assert usuario_service.registrar(db, identidad, datos).id == "uid"


def test_fallo_borrado_conserva_cuenta_para_reintentar(db, monkeypatch):
    db.add(Usuario(id="uid", email="uid@test.com", nombre="Prueba", rol="CLIENTE", activo=True))
    db.commit()
    borrar = Mock(side_effect=RuntimeError("Firebase no responde"))
    monkeypatch.setattr(firebase_auth, "eliminar_cuenta", borrar)
    with pytest.raises(RuntimeError):
        usuario_service.eliminar_cuenta(db, "uid")
    usuario = db.get(Usuario, "uid")
    assert usuario.eliminado_en is None and usuario.email == "uid@test.com" and usuario.activo
    borrar.side_effect = None
    usuario_service.eliminar_cuenta(db, "uid")
    assert db.get(Usuario, "uid").eliminado_en is not None


def test_sin_credenciales_no_contacta_con_firebase(monkeypatch):
    monkeypatch.setattr(firebase_auth, "FIREBASE_CREDENCIALES", "")
    iniciar = Mock()
    monkeypatch.setattr(firebase_admin, "initialize_app", iniciar)
    firebase_auth.inicializar()
    firebase_auth.asignar_rol("uid", "CLIENTE")
    firebase_auth.eliminar_cuenta("uid")
    iniciar.assert_not_called()
