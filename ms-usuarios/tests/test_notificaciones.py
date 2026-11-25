import logging
from datetime import datetime, timezone
import pytest
from model.models import PreferenciasNotificacion, Usuario
from service.notificaciones import notificar


@pytest.mark.parametrize("push,email,tokens,canales,esperados", [
    (True, True, ["token"], ("push", "email"), {"push", "email"}),
    (False, True, ["token"], ("push",), set()),
    (True, False, ["token"], ("email",), set()),
    (False, False, ["token"], ("push", "email"), set()),
    (True, True, [], ("push", "email"), {"email"}),
    (True, True, ["token"], ("email",), {"email"}),
])
def test_respeta_preferencias_y_canales(db, caplog, push, email, tokens, canales, esperados):
    db.add(Usuario(id="u", email="u@test.com", rol="CLIENTE", activo=True))
    db.flush()
    db.add(PreferenciasNotificacion(usuario_id="u", push=push, email=email, fcm_tokens=tokens))
    db.commit()
    caplog.set_level(logging.INFO, logger="notificaciones")
    notificar(db, {"u"}, "Título", "Cuerpo", canales=canales)
    assert {r.message.split()[0].strip("[]") for r in caplog.records} == esperados


def test_no_notifica_a_inactivos_eliminados_o_inexistentes(db, caplog):
    db.add_all([
        Usuario(id="inactivo", email="i@test.com", rol="CLIENTE", activo=False),
        Usuario(id="eliminado", email="e@test.com", rol="CLIENTE", activo=True,
                eliminado_en=datetime.now(timezone.utc)),
    ])
    db.commit()
    caplog.set_level(logging.INFO, logger="notificaciones")
    notificar(db, {"inactivo", "eliminado", "inexistente"}, "Título", "Cuerpo")
    assert not caplog.records
