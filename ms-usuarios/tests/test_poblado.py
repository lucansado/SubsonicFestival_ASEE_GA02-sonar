from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import select

from config.database import SessionLocal
from model.models import ArtistaFavorito, Proveedor, Usuario
from scripts import poblar_bd


@pytest.fixture
def publicar(monkeypatch, bd_limpia):
    publicador = Mock()
    monkeypatch.setattr(poblar_bd, "publicar", publicador)
    return publicador


def test_poblado_publica_registros_y_favoritos_ya_guardados(publicar):
    def comprobar_guardado(tipo, datos):
        with SessionLocal() as db:
            usuario = db.get(Usuario, datos["usuario_id"])
            assert usuario is not None
            if tipo == "usuarios.usuario.registrado":
                assert usuario.rol == datos["rol"]
            else:
                favorito = db.get(ArtistaFavorito, (usuario.id, UUID(datos["artista_id"])))
                assert favorito.artista_nombre == datos["artista_nombre"]

    publicar.side_effect = comprobar_guardado
    poblar_bd.poblar()
    registros = [c.args[1] for c in publicar.call_args_list if c.args[0] == "usuarios.usuario.registrado"]
    assert registros == [
        {"usuario_id": "uid-cliente-david", "rol": "CLIENTE"},
        {"usuario_id": "uid-proveedor-ana", "rol": "PROVEEDOR"},
        {"usuario_id": "uid-admin-jose", "rol": "ADMIN"},
        {"usuario_id": "uid-staff-lucia", "rol": "STAFF"},
    ]
    favoritos = [c.args[1] for c in publicar.call_args_list if c.args[0] == "usuarios.favorito.anadido"]
    assert len(favoritos) == 3
    assert {f["usuario_id"] for f in favoritos} == {"uid-cliente-david"}
    assert {(f["artista_id"], f["artista_nombre"]) for f in favoritos} == {
        ("22222222-2222-4222-8222-000000000001", "Martin Garrix"),
        ("22222222-2222-4222-8222-000000000004", "Armin van Buuren"),
        ("22222222-2222-4222-8222-000000000009", "Skrillex"),
    }
    with SessionLocal() as db:
        assert db.get(Proveedor, "uid-proveedor-ana").validado is True


def test_repetir_poblado_no_duplica_datos_ni_eventos(publicar):
    poblar_bd.poblar()
    publicar.reset_mock()
    poblar_bd.poblar()
    publicar.assert_not_called()
    with SessionLocal() as db:
        assert len(db.scalars(select(Usuario)).all()) == 4
        assert len(db.scalars(select(ArtistaFavorito)).all()) == 3


def test_completa_poblado_parcial_sin_sobrescribir_el_perfil_ni_favoritos(publicar):
    with SessionLocal() as db:
        db.add(Usuario(id="uid-cliente-david", email="david@demo.test", nombre="David editado", rol="CLIENTE"))
        db.commit()
        db.add(ArtistaFavorito(usuario_id="uid-cliente-david", artista_id=poblar_bd.FAVORITOS_DAVID[0][0],
                              artista_nombre="Nombre actualizado"))
        db.commit()
    poblar_bd.poblar()
    assert publicar.call_count == 5  # tres usuarios y dos favoritos faltantes
    assert not any(c.args == ("usuarios.usuario.registrado", {"usuario_id": "uid-cliente-david", "rol": "CLIENTE"})
                   for c in publicar.call_args_list)
    with SessionLocal() as db:
        assert db.get(Usuario, "uid-cliente-david").nombre == "David editado"
        assert db.get(ArtistaFavorito, ("uid-cliente-david", poblar_bd.FAVORITOS_DAVID[0][0])).artista_nombre == "Nombre actualizado"


def test_no_anade_favoritos_a_una_cuenta_eliminada(publicar):
    from datetime import datetime, timezone

    with SessionLocal() as db:
        db.add(Usuario(id="uid-cliente-david", email="david@eliminado.invalid", rol="CLIENTE", activo=False,
                       eliminado_en=datetime.now(timezone.utc)))
        db.commit()
    poblar_bd.poblar()
    assert all(c.args[0] == "usuarios.usuario.registrado" for c in publicar.call_args_list)
    with SessionLocal() as db:
        assert db.scalars(select(ArtistaFavorito)).all() == []
