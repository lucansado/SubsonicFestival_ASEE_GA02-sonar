from types import SimpleNamespace
from unittest.mock import Mock
from firebase_admin import auth
import pytest
from scripts import comprobar_firebase as script


@pytest.fixture
def entorno(monkeypatch):
    app = object()
    monkeypatch.setattr(script, "_firebase", lambda: app)
    cliente = Mock()
    cliente.delete.return_value.status_code = 204
    contexto = Mock()
    contexto.__enter__ = Mock(return_value=cliente)
    contexto.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(script.httpx, "Client", Mock(return_value=contexto))
    crear, borrar, obtener = Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, "create_user", crear)
    monkeypatch.setattr(auth, "delete_user", borrar)
    monkeypatch.setattr(auth, "get_user", obtener)
    return app, cliente, crear, borrar, obtener


@pytest.mark.parametrize(
    ("api_url", "base_url"),
    [
        ("http://localhost:8003", "http://127.0.0.1:8003"),
        ("http://127.0.0.1:8003/", "http://127.0.0.1:8003"),
        ("http://[::1]:8003", "http://[::1]:8003"),
    ],
)
def test_comprobacion_real_usa_solo_la_cuenta_creada(entorno, api_url, base_url):
    app, cliente, crear, borrar, obtener = entorno
    obtener.side_effect = [SimpleNamespace(custom_claims={"rol": "CLIENTE"}), auth.UserNotFoundError("borrado")]
    script.comprobar(api_url)
    opciones_cliente = script.httpx.Client.call_args.kwargs
    assert opciones_cliente["base_url"] == base_url
    assert opciones_cliente["follow_redirects"] is False
    assert opciones_cliente["trust_env"] is False
    uid = crear.call_args.kwargs["uid"]
    assert uid.startswith("prueba-usuarios-")
    assert cliente.post.call_args.kwargs["json"]["rol"] == "CLIENTE"
    assert cliente.delete.call_count == 1
    assert all(c.args[0] == uid for c in obtener.call_args_list)
    borrar.assert_called_once_with(uid, app=app)


def test_no_borra_si_no_pudo_crear_la_cuenta(entorno):
    _, cliente, crear, borrar, _ = entorno
    crear.side_effect = RuntimeError("no creado")
    with pytest.raises(RuntimeError):
        script.comprobar("http://localhost:8003")
    borrar.assert_not_called()
    cliente.post.assert_not_called()
    cliente.delete.assert_not_called()


def test_limpia_si_no_se_asigno_el_claim(entorno):
    app, cliente, crear, borrar, obtener = entorno
    obtener.return_value = SimpleNamespace(custom_claims=None)
    with pytest.raises(RuntimeError, match="claim"):
        script.comprobar("http://localhost:8003")
    cliente.delete.assert_called_once()
    borrar.assert_called_once_with(crear.call_args.kwargs["uid"], app=app)


def test_rechaza_modo_simulado_antes_de_crear(entorno, monkeypatch):
    monkeypatch.setattr(script, "_firebase", lambda: None)
    with pytest.raises(SystemExit, match="FIREBASE_CREDENCIALES"):
        script.comprobar("http://localhost:8003")
    entorno[2].assert_not_called()


@pytest.mark.parametrize(
    "api_url",
    ["https://api.example.invalid", "http://localhost:8004", "http://localhost:8003/ruta"],
)
def test_rechaza_origen_no_autorizado_antes_de_conectarse(entorno, monkeypatch, api_url):
    firebase = Mock()
    monkeypatch.setattr(script, "_firebase", firebase)
    with pytest.raises(SystemExit, match="origen HTTP local"):
        script.comprobar(api_url)
    firebase.assert_not_called()
    script.httpx.Client.assert_not_called()
    entorno[2].assert_not_called()
