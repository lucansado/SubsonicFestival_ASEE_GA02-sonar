import logging
from urllib.parse import quote
from uuid import uuid4

import pytest
from config.database import SessionLocal
from eventos.manejadores import manejar
from model.models import ArtistaFavorito, Entrada, PreferenciasNotificacion, Usuario

RUTA = "/api/v1/usuarios/me/dispositivos"
CABECERAS = {"X-User-Id": "cliente-dispositivos"}
TOKEN = "dispositivo:APA91bH-ejemplo"
OTRO_TOKEN = "otro-dispositivo:APA91bH-ejemplo"


@pytest.fixture
def cliente_con_perfil(cliente_http):
    with SessionLocal.begin() as db:
        db.add(Usuario(id=CABECERAS["X-User-Id"], email="dispositivos@test.com", rol="CLIENTE", activo=True))
    return cliente_http


def registrar(cliente, token=TOKEN):
    respuesta = cliente.post(RUTA, headers=CABECERAS, json={"fcm_token": token, "plataforma": "WEB"})
    assert respuesta.status_code == 201


def tokens_guardados(usuario_id=CABECERAS["X-User-Id"]):
    # Otra sesión: comprobar lo persistido, no solo el objeto en memoria del endpoint.
    with SessionLocal() as db:
        preferencias = db.get(PreferenciasNotificacion, usuario_id)
        return list(preferencias.fcm_tokens) if preferencias is not None else None


@pytest.mark.parametrize("codificado", [False, True])
def test_borra_uno_de_dos_tokens_y_persiste_el_otro(cliente_con_perfil, codificado):
    registrar(cliente_con_perfil)
    registrar(cliente_con_perfil, OTRO_TOKEN)
    token_ruta = quote(TOKEN, safe="") if codificado else TOKEN
    respuesta = cliente_con_perfil.delete(f"{RUTA}/{token_ruta}", headers=CABECERAS)
    assert respuesta.status_code == 204 and respuesta.content == b""
    assert tokens_guardados() == [OTRO_TOKEN]
    # La baja puede repetirse al cerrar sesión.
    assert cliente_con_perfil.delete(f"{RUTA}/{token_ruta}", headers=CABECERAS).status_code == 204
    assert tokens_guardados() == [OTRO_TOKEN]


def test_borrar_token_inexistente_conserva_los_registrados(cliente_con_perfil):
    registrar(cliente_con_perfil)
    respuesta = cliente_con_perfil.delete(f"{RUTA}/no-registrado", headers=CABECERAS)
    assert respuesta.status_code == 204 and respuesta.content == b""
    assert tokens_guardados() == [TOKEN]


def test_borrar_sin_preferencias_no_las_crea(cliente_con_perfil):
    respuesta = cliente_con_perfil.delete(f"{RUTA}/{TOKEN}", headers=CABECERAS)
    assert respuesta.status_code == 204 and respuesta.content == b""
    assert tokens_guardados() is None


def test_borrar_sin_autenticar_no_modifica_tokens(cliente_con_perfil):
    registrar(cliente_con_perfil)
    respuesta = cliente_con_perfil.delete(f"{RUTA}/{TOKEN}")
    assert respuesta.status_code == 401 and respuesta.json()["codigo"] == "NO_AUTENTICADO"
    assert tokens_guardados() == [TOKEN]


@pytest.mark.parametrize("rol", ["CLIENTE", "PROVEEDOR", "ADMIN", "STAFF"])
def test_cualquier_rol_autenticado_puede_dar_de_baja_su_dispositivo(cliente_con_perfil, rol):
    registrar(cliente_con_perfil)
    with SessionLocal.begin() as db:
        db.get(Usuario, CABECERAS["X-User-Id"]).rol = rol
    respuesta = cliente_con_perfil.delete(f"{RUTA}/{TOKEN}", headers=CABECERAS | {"X-User-Rol": rol})
    assert respuesta.status_code == 204
    assert tokens_guardados() == []


def test_no_borra_tokens_de_otro_usuario(cliente_con_perfil):
    registrar(cliente_con_perfil)
    with SessionLocal.begin() as db:
        db.add(Usuario(id="otro-usuario", email="otro@test.com", rol="CLIENTE", activo=True))
        db.flush()
        db.add(PreferenciasNotificacion(usuario_id="otro-usuario", push=True, email=True, fcm_tokens=[TOKEN]))
    assert cliente_con_perfil.delete(f"{RUTA}/{TOKEN}", headers=CABECERAS).status_code == 204
    assert tokens_guardados() == []
    assert tokens_guardados("otro-usuario") == [TOKEN]


def test_autenticado_sin_perfil_tambien_recibe_204(cliente_http):
    respuesta = cliente_http.delete(f"{RUTA}/{TOKEN}", headers=CABECERAS)
    assert respuesta.status_code == 204
    assert tokens_guardados() is None


def test_baja_del_ultimo_token_silencia_push_por_cambio_de_escaleta(cliente_con_perfil, caplog):
    registrar(cliente_con_perfil)
    artista_id = uuid4()
    with SessionLocal.begin() as db:
        db.add(ArtistaFavorito(usuario_id=CABECERAS["X-User-Id"], artista_id=artista_id, artista_nombre="Artista"))
        db.add(Entrada(id="entrada-dispositivo", usuario_id=CABECERAS["X-User-Id"], evento_id="evento-prueba",
                       tipo_pase="DAY", estado="ACTIVA", precio_pagado=50, codigo_qr="qr"))
    datos = {"evento_id": "evento-prueba", "artista_id": str(artista_id), "artista_nombre": "Artista",
             "inicio_nuevo": "2099-07-18T22:00:00Z"}
    caplog.set_level(logging.INFO, logger="notificaciones")
    manejar({"id_evento": str(uuid4()), "tipo": "escaleta.pase.modificado", "datos": datos})
    assert any(r.name == "notificaciones" and r.getMessage().startswith("[push] cliente-dispositivos ")
               for r in caplog.records)
    assert cliente_con_perfil.delete(f"{RUTA}/{TOKEN}", headers=CABECERAS).status_code == 204
    assert tokens_guardados() == []
    caplog.clear()
    # ID nuevo: el silencio debe deberse a la baja, no a la deduplicación de eventos.
    manejar({"id_evento": str(uuid4()), "tipo": "escaleta.pase.modificado", "datos": datos})
    assert not any(r.name == "notificaciones" and "[push]" in r.getMessage() for r in caplog.records)
