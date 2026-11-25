# ms-usuarios/service/notificaciones.py
# Envío de notificaciones push (Firebase Cloud Messaging) y email.
# Envío SIMULADO: se registra en el log respetando los canales solicitados y las preferencias.
import logging
from sqlalchemy.orm import Session
from model.factory.factory_dao import DAOFactory

log = logging.getLogger("notificaciones")
usuario_dao = DAOFactory.get_usuario_dao()


def notificar(db: Session, usuario_ids: set[str], titulo: str, cuerpo: str, *,
              canales: tuple[str, ...] = ("push", "email")) -> None:
    for usuario_id in usuario_ids:
        usuario = usuario_dao.obtener(db, usuario_id)
        if usuario is None or not usuario.activo:
            continue
        preferencias = usuario_dao.obtener_preferencias(db, usuario_id)
        push = "push" in canales and (preferencias.push if preferencias else True)
        email = "email" in canales and (preferencias.email if preferencias else True)
        if push and preferencias and preferencias.fcm_tokens:
            log.info("[push] %s (%s dispositivos): %s - %s", usuario_id, len(preferencias.fcm_tokens), titulo, cuerpo)
        if email:
            log.info("[email] %s: %s - %s", usuario_id, titulo, cuerpo)
