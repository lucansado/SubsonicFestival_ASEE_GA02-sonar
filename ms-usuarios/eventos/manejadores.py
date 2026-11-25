"""Una sesión y una transacción por mensaje; los errores se devuelven al consumidor."""
import logging
from uuid import UUID
from config.database import SessionLocal
from eventos.consumidor import Consumidor
from model.models import EventoProcesado
from service import entrada_service, eventos_service

log = logging.getLogger("manejadores")

CLAVES = [
    "escaleta.pase.modificado", "escaleta.pase.cancelado", "espacios.evento.cancelado",
    "escaleta.artista.actualizado", "escaleta.publicada", "espacios.alquiler.solicitado",
    "espacios.alquiler.aprobado", "espacios.alquiler.rechazado", "tienda.pedido.creado",
    "tienda.pedido.actualizado", "tienda.stock.bajo",
]


def manejar(sobre: dict) -> None:
    tipo, datos = sobre["tipo"], sobre["datos"]
    if tipo not in CLAVES:
        raise ValueError(f"Tipo de evento no soportado: {tipo}")
    if not isinstance(datos, dict):
        raise ValueError("datos debe ser un objeto")
    id_evento = str(UUID(sobre["id_evento"]))
    with SessionLocal.begin() as db:
        if db.get(EventoProcesado, id_evento) is not None:
            log.info("Evento ya procesado: %s", id_evento)
            return
        # La clave primaria evita que dos consumidores tramiten a la vez el mismo mensaje.
        # Si cualquiera de las operaciones falla, la marca también se revierte.
        db.add(EventoProcesado(id_evento=id_evento, tipo=tipo))
        db.flush()
        if tipo in ("escaleta.pase.modificado", "escaleta.pase.cancelado"):
            entrada_service.al_modificar_pase(db, datos, cancelado=tipo.endswith(".cancelado"))
        elif tipo == "espacios.evento.cancelado":
            entrada_service.al_cancelar_evento(db, datos["evento_id"], datos.get("motivo"))
        elif tipo == "escaleta.artista.actualizado":
            entrada_service.al_actualizar_artista(db, UUID(datos["artista_id"]), datos["nombre"])
        elif tipo == "escaleta.publicada":
            eventos_service.al_publicar_escaleta(db, datos)
        elif tipo == "espacios.alquiler.solicitado":
            eventos_service.al_solicitar_alquiler(db, datos)
        elif tipo in ("espacios.alquiler.aprobado", "espacios.alquiler.rechazado"):
            eventos_service.al_resolver_alquiler(db, datos, aprobado=tipo.endswith(".aprobado"))
        elif tipo == "tienda.pedido.creado":
            eventos_service.al_crear_pedido(db, datos)
        elif tipo == "tienda.pedido.actualizado":
            eventos_service.al_actualizar_pedido(db, datos)
        elif tipo == "tienda.stock.bajo":
            eventos_service.al_bajar_stock(db, datos)


consumidor = Consumidor(cola="ms-usuarios", claves=CLAVES, manejador=manejar)
