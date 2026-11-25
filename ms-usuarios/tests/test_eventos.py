import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from config.database import SessionLocal
from eventos import manejadores
from model.models import ArtistaFavorito, Entrada, EventoProcesado, PreferenciasNotificacion, Usuario
from service import entrada_service


def sobre(tipo, datos):
    return {"id_evento": str(uuid4()), "tipo": tipo, "version": 1, "origen": "prueba",
            "fecha": datetime.now(timezone.utc).isoformat(), "correlation_id": str(uuid4()), "datos": datos}


@pytest.fixture
def escenario(db):
    artista = uuid4()
    for uid, rol, activo, eliminado in [
        ("cliente", "CLIENTE", True, False), ("sin-favorito", "CLIENTE", True, False),
        ("sin-entrada", "CLIENTE", True, False), ("cancelada", "CLIENTE", True, False),
        ("otro-evento", "CLIENTE", True, False), ("proveedor", "PROVEEDOR", True, False),
        ("admin", "ADMIN", True, False), ("admin-inactivo", "ADMIN", False, False),
        ("admin-borrado", "ADMIN", False, True),
    ]:
        db.add(Usuario(id=uid, email=f"{uid}@test.com", rol=rol, activo=activo,
                       eliminado_en=datetime.now(timezone.utc) if eliminado else None))
        db.flush()
        db.add(PreferenciasNotificacion(usuario_id=uid, push=True, email=True, fcm_tokens=[f"token-{uid}"]))
    for uid in ("cliente", "sin-entrada", "cancelada", "otro-evento"):
        db.add(ArtistaFavorito(usuario_id=uid, artista_id=artista, artista_nombre="Nombre anterior"))
    for numero, uid, estado, evento in [
        (1, "cliente", "ACTIVA", "evento-1"), (2, "cliente", "ACTIVA", "evento-1"),
        (3, "sin-favorito", "ACTIVA", "evento-1"), (4, "cancelada", "CANCELADA", "evento-1"),
        (5, "otro-evento", "ACTIVA", "evento-2"), (6, "cliente", "CANCELACION_SOLICITADA", "evento-1"),
    ]:
        db.add(Entrada(id=f"entrada-{numero}", usuario_id=uid, evento_id=evento, tipo_pase="DAY",
                       estado=estado, precio_pagado=Decimal("50"), codigo_qr="qr", pago_ref=f"pago-{numero}"))
    db.commit()
    return artista


def avisos(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "notificaciones"]


@pytest.mark.parametrize("tipo,cancelado", [
    ("escaleta.pase.modificado", False), ("escaleta.pase.cancelado", True),
])
def test_pases_solo_favorito_con_entrada_y_sin_duplicados(escenario, caplog, tipo, cancelado):
    caplog.set_level(logging.INFO)
    evento = sobre(tipo, {"artista_id": str(escenario), "evento_id": "evento-1",
                         "artista_nombre": "Artista", "inicio_nuevo": "2099-07-18T22:00:00Z",
                         "motivo": "Lluvia"})
    manejadores.manejar(evento)
    manejadores.manejar(evento)
    mensajes = avisos(caplog)
    assert len(mensajes) == 1
    assert mensajes[0].startswith("[push] cliente ")
    assert ("Actuación cancelada" if cancelado else "Nuevo horario") in mensajes[0]
    assert ("Lluvia" if cancelado else "2099-07-18T22:00:00Z") in mensajes[0]


@pytest.mark.parametrize("tipo,datos,destinos,canales,texto", [
    ("escaleta.publicada", {"evento_id": "evento-1", "version": 2, "dias": []},
     {"cliente", "sin-favorito"}, {"push"}, "Escaleta publicada"),
    ("espacios.alquiler.solicitado", {"alquiler_id": "a-1", "proveedor_id": "proveedor", "espacio_id": "e-1"},
     {"admin"}, {"push", "email"}, "Nueva solicitud"),
    ("espacios.alquiler.aprobado", {"alquiler_id": "a-1", "proveedor_id": "proveedor", "espacio_id": "e-1"},
     {"proveedor"}, {"push", "email"}, "Alquiler aprobado"),
    ("espacios.alquiler.rechazado", {"alquiler_id": "a-1", "proveedor_id": "proveedor", "espacio_id": "e-1"},
     {"proveedor"}, {"push", "email"}, "Alquiler rechazado"),
    ("tienda.pedido.creado", {"pedido_id": "p-1", "usuario_id": "cliente", "importe_total": 25},
     {"cliente"}, {"email"}, "Pedido confirmado"),
    ("tienda.pedido.actualizado", {"pedido_id": "p-1", "usuario_id": "cliente", "estado": "ENVIADO"},
     {"cliente"}, {"email"}, "en camino"),
    ("tienda.pedido.actualizado", {"pedido_id": "p-1", "usuario_id": "cliente", "estado": "LISTO_RECOGIDA",
                                   "evento_id_recogida": "evento-1"},
     {"cliente"}, {"email"}, "Recógelo en el evento evento-1"),
    ("tienda.stock.bajo", {"producto_id": "camiseta", "variante_id": "v-1", "talla": "M", "stock": 2, "umbral": 5},
     {"admin"}, {"push", "email"}, "quedan 2 unidades"),
])
def test_avisos_por_evento(escenario, caplog, tipo, datos, destinos, canales, texto):
    caplog.set_level(logging.INFO)
    evento = sobre(tipo, datos)
    manejadores.manejar(evento)
    manejadores.manejar(evento)
    mensajes = avisos(caplog)
    assert len(mensajes) == len(destinos) * len(canales)
    assert {m.split()[1].rstrip(":") for m in mensajes} == destinos
    assert {m.split()[0].strip("[]") for m in mensajes} == canales
    assert all(texto in m for m in mensajes)


def test_cancelacion_reembolsa_y_publica_una_vez(escenario, monkeypatch, caplog):
    reembolsar, publicar = Mock(), Mock()
    monkeypatch.setattr(entrada_service.pasarela_pago, "reembolsar", reembolsar)
    monkeypatch.setattr(entrada_service, "publicar", publicar)
    caplog.set_level(logging.INFO)
    evento = sobre("espacios.evento.cancelado", {"evento_id": "evento-1", "motivo": "Temporal"})
    manejadores.manejar(evento)
    manejadores.manejar(evento)
    # Incluso otro sobre con el mismo cambio de estado no reembolsa de nuevo.
    manejadores.manejar(sobre(evento["tipo"], evento["datos"]))
    assert reembolsar.call_count == publicar.call_count == 4
    assert {c.args[0] for c in reembolsar.call_args_list} == {"pago-1", "pago-2", "pago-3", "pago-6"}
    assert all(c.args[0] == "usuarios.entrada.cancelada" for c in publicar.call_args_list)
    with SessionLocal() as sesion:
        assert sesion.get(Entrada, "entrada-1").estado == "CANCELADA"
        assert sesion.get(Entrada, "entrada-6").motivo_cancelacion == "Evento cancelado: Temporal"
        assert sesion.get(Entrada, "entrada-5").estado == "ACTIVA"
    assert len(avisos(caplog)) == 4  # dos clientes, dos canales


def test_actualizar_artista_en_todos_los_favoritos(escenario):
    manejadores.manejar(sobre("escaleta.artista.actualizado", {"artista_id": str(escenario), "nombre": "Nombre nuevo"}))
    with SessionLocal() as sesion:
        assert set(sesion.scalars(select(ArtistaFavorito.artista_nombre)).all()) == {"Nombre nuevo"}


def test_error_revierte_cambios_y_permite_reintento(escenario, monkeypatch):
    evento = sobre("escaleta.artista.actualizado", {"artista_id": str(escenario), "nombre": "Nuevo"})
    original = entrada_service.al_actualizar_artista

    def falla(db, artista_id, nombre):
        original(db, artista_id, nombre)
        raise RuntimeError("fallo después de escribir")

    monkeypatch.setattr(entrada_service, "al_actualizar_artista", falla)
    with pytest.raises(RuntimeError):
        manejadores.manejar(evento)
    with SessionLocal() as sesion:
        assert sesion.get(EventoProcesado, evento["id_evento"]) is None
        assert set(sesion.scalars(select(ArtistaFavorito.artista_nombre)).all()) == {"Nombre anterior"}
    monkeypatch.setattr(entrada_service, "al_actualizar_artista", original)
    manejadores.manejar(evento)
    with SessionLocal() as sesion:
        assert sesion.get(EventoProcesado, evento["id_evento"]) is not None


@pytest.mark.parametrize("datos", [{}, {"artista_id": "no-es-uuid", "nombre": "X"}])
def test_evento_invalido_no_queda_marcado(bd_limpia, datos):
    evento = sobre("escaleta.artista.actualizado", datos)
    with pytest.raises((KeyError, ValueError)):
        manejadores.manejar(evento)
    with SessionLocal() as sesion:
        assert sesion.get(EventoProcesado, evento["id_evento"]) is None
