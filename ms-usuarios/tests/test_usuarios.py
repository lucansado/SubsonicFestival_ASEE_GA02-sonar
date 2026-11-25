# ms-usuarios/tests/test_usuarios.py
import uuid
import pytest
from config.errores import ErrorApi
from conftest import ADMIN, CLIENTE, OTRO_CLIENTE, STAFF
from service import clientes

API = "/api/v1"
ALTA_CLIENTE = CLIENTE | {"X-User-Email": "cliente1@test.com"}


@pytest.fixture
def espacios_simulado(monkeypatch):
    """Sustituye las llamadas a ms-espacios: cupo de 1 entrada por defecto."""
    estado = {"cupo": 1, "liberadas": []}

    def reservar(evento_id, tipo_pase, usuario_id):
        if evento_id != "evento-belgium":
            raise ErrorApi(404, "EVENTO_NO_ENCONTRADO", "No existe")
        if estado["cupo"] <= 0:
            raise ErrorApi(409, "SIN_CUPO", "No quedan entradas")
        estado["cupo"] -= 1
        return {"reserva_id": str(uuid.uuid4()), "evento_id": evento_id, "tipo_pase": tipo_pase, "precio": 199.0,
                "expira_en": "2026-07-01T10:10:00Z", "evento_titulo": "Subsonic Belgium",
                "fecha_inicio": "2099-07-18", "fecha_fin": "2099-07-27"}

    monkeypatch.setattr(clientes, "reservar_aforo", reservar)
    monkeypatch.setattr(clientes, "liberar_aforo", lambda reserva_id: estado["liberadas"].append(reserva_id))
    return estado


def registrar_cliente(c):
    r = c.post(f"{API}/usuarios", headers=ALTA_CLIENTE, json={"nombre": "Paula", "apellidos": "Jiménez Cruz",
                                                               "rol": "CLIENTE"})
    assert r.status_code == 201, r.text
    return r.json()


def comprar(c, token="tok_ok", evento="evento-belgium"):
    return c.post(f"{API}/usuarios/me/entradas", headers=CLIENTE,
                  json={"evento_id": evento, "tipo_pase": "WEEKEND", "token_pago": token})


def test_registro_y_perfil(cliente_http):
    c = cliente_http
    assert c.get(f"{API}/usuarios/me", headers={"X-User-Id": "cliente-1"}).status_code == 404
    usuario = registrar_cliente(c)
    assert usuario["rol"] == "CLIENTE" and usuario["email"] == "cliente1@test.com"
    assert c.post(f"{API}/usuarios", headers=ALTA_CLIENTE, json={"nombre": "X", "rol": "CLIENTE"}).status_code == 409
    # No se puede registrar uno mismo como admin
    r = c.post(f"{API}/usuarios", headers={"X-User-Id": "x", "X-User-Email": "x@x.com"},
               json={"nombre": "X", "rol": "ADMIN"})
    assert r.status_code == 400
    r = c.patch(f"{API}/usuarios/me", headers=CLIENTE, json={"telefono": "+34 611 000 000"})
    assert r.json()["telefono"] == "+34 611 000 000"
    assert c.patch(f"{API}/usuarios/me", headers=CLIENTE, json={}).status_code == 400


def test_proveedor_y_administracion(cliente_http):
    c = cliente_http
    prov = {"X-User-Id": "prov-1", "X-User-Rol": "PROVEEDOR", "X-User-Email": "prov@test.com"}
    r = c.post(f"{API}/usuarios", headers=prov, json={
        "nombre": "Ana", "rol": "PROVEEDOR", "proveedor": {"nombre_comercial": "Frituras Boom", "tipo_servicio": "Comida"}})
    assert r.json()["proveedor"]["validado"] is False
    assert c.get(f"{API}/proveedores?validado=false", headers=ADMIN).headers["X-Total-Count"] == "1"
    r = c.patch(f"{API}/proveedores/prov-1", headers=ADMIN, json={"validado": True})
    assert r.json()["proveedor"]["validado"] is True

    registrar_cliente(c)
    assert c.get(f"{API}/usuarios", headers=CLIENTE).status_code == 403
    assert c.get(f"{API}/usuarios?q=paula", headers=ADMIN).headers["X-Total-Count"] == "1"
    r = c.patch(f"{API}/usuarios/cliente-1", headers=ADMIN, json={"rol": "STAFF"})
    assert r.json()["rol"] == "STAFF"


def test_compra_y_validacion_en_puerta(cliente_http, espacios_simulado):
    c = cliente_http
    registrar_cliente(c)
    r = comprar(c)
    assert r.status_code == 201, r.text
    entrada = r.json()
    assert entrada["estado"] == "ACTIVA" and entrada["evento_fechas"] == "18 – 27 Julio 2099"
    assert r.headers["Location"].endswith(entrada["id"])

    # Sin cupo -> 409 reenviado desde ms-espacios
    assert comprar(c).status_code == 409

    url = f"{API}/entradas/validaciones"
    falso = entrada["codigo_qr"][:-4] + "0000"
    assert c.post(url, headers=STAFF, json={"codigo_qr": falso, "evento_id": "evento-belgium"}).status_code == 400
    assert c.post(url, headers=STAFF, json={"codigo_qr": entrada["codigo_qr"],
                                            "evento_id": "evento-brasil"}).status_code == 409
    assert c.post(url, headers=CLIENTE, json={"codigo_qr": entrada["codigo_qr"],
                                              "evento_id": "evento-belgium"}).status_code == 403
    r = c.post(url, headers=STAFF, json={"codigo_qr": entrada["codigo_qr"], "evento_id": "evento-belgium"})
    assert r.status_code == 201 and r.json()["titular"] == "Paula Jiménez Cruz"
    r = c.post(url, headers=STAFF, json={"codigo_qr": entrada["codigo_qr"], "evento_id": "evento-belgium"})
    assert r.status_code == 409 and r.json()["codigo"] == "ENTRADA_USADA"


def test_pago_rechazado_libera_la_reserva(cliente_http, espacios_simulado):
    c = cliente_http
    registrar_cliente(c)
    assert comprar(c, token="tok_rechazado").status_code == 402
    assert len(espacios_simulado["liberadas"]) == 1
    assert comprar(c, evento="evento-inexistente").status_code == 404
    assert c.get(f"{API}/usuarios/me/entradas", headers=CLIENTE).json() == []


def test_espacios_caido_responde_503(cliente_http, monkeypatch):
    c = cliente_http
    registrar_cliente(c)
    monkeypatch.setattr(clientes, "ESPACIOS_URL", "http://127.0.0.1:9")  # puerto sin servicio
    monkeypatch.setattr(clientes, "TIMEOUT_SEGUNDOS", 0.2)
    r = comprar(c)
    assert r.status_code == 503 and r.headers["Retry-After"] == "5"


def test_cancelacion_de_entrada(cliente_http, espacios_simulado):
    c = cliente_http
    registrar_cliente(c)
    entrada = comprar(c).json()
    url = f"{API}/usuarios/me/entradas/{entrada['id']}/cancelaciones"
    assert c.get(f"{API}/usuarios/me/entradas/{entrada['id']}", headers=OTRO_CLIENTE).status_code == 404
    assert c.post(url, headers=CLIENTE, json={"motivo": "no"}).status_code == 400  # motivo demasiado corto
    r = c.post(url, headers=CLIENTE, json={"motivo": "No puedo ir"})
    assert r.status_code == 201 and r.json()["estado"] == "CANCELACION_SOLICITADA"
    assert c.post(url, headers=CLIENTE, json={"motivo": "No puedo ir"}).status_code == 409

    # Con una entrada pendiente no se puede borrar la cuenta
    assert c.delete(f"{API}/usuarios/me", headers=CLIENTE).status_code == 409

    pendientes = c.get(f"{API}/entradas?estado=CANCELACION_SOLICITADA", headers=ADMIN)
    assert pendientes.headers["X-Total-Count"] == "1"
    r = c.patch(f"{API}/entradas/{entrada['id']}", headers=ADMIN, json={"estado": "CANCELADA"})
    assert r.json()["estado"] == "CANCELADA"
    assert c.patch(f"{API}/entradas/{entrada['id']}", headers=ADMIN, json={"estado": "ACTIVA"}).status_code == 409

    # Ya sin entradas activas: borrado RGPD
    assert c.delete(f"{API}/usuarios/me", headers=CLIENTE).status_code == 204
    assert c.get(f"{API}/usuarios/me", headers=CLIENTE).status_code == 404
    assert c.post(f"{API}/usuarios", headers=ALTA_CLIENTE, json={"nombre": "X", "rol": "CLIENTE"}).status_code == 409


def test_favoritos_y_preferencias(cliente_http, monkeypatch):
    c = cliente_http
    registrar_cliente(c)
    monkeypatch.setattr(clientes, "nombre_artista", lambda artista_id: "Armin van Buuren")
    artista = str(uuid.uuid4())
    r = c.post(f"{API}/usuarios/me/favoritos", headers=CLIENTE, json={"artista_id": artista})
    assert r.status_code == 201 and r.json()["artista_nombre"] == "Armin van Buuren"
    assert c.post(f"{API}/usuarios/me/favoritos", headers=CLIENTE, json={"artista_id": artista}).status_code == 409
    assert len(c.get(f"{API}/usuarios/me/favoritos", headers=CLIENTE).json()) == 1
    assert c.delete(f"{API}/usuarios/me/favoritos/{artista}", headers=CLIENTE).status_code == 204
    assert c.delete(f"{API}/usuarios/me/favoritos/{artista}", headers=CLIENTE).status_code == 404

    assert c.get(f"{API}/usuarios/me/preferencias-notificacion", headers=CLIENTE).json() == {"push": True, "email": True}
    assert c.put(f"{API}/usuarios/me/preferencias-notificacion", headers=CLIENTE,
                 json={"push": False, "email": True}).json()["push"] is False
    assert c.post(f"{API}/usuarios/me/dispositivos", headers=CLIENTE,
                  json={"fcm_token": "abc", "plataforma": "ANDROID"}).status_code == 201
