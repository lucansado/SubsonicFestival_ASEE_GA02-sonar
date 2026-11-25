# eventos/publicador.py  (plantilla común: rama infra, carpeta plantilla-mensajeria)
# Publicación de eventos con el sobre común de la ASEE (memoria, apartado 4.1) en RabbitMQ.
# - Exchange topic "subsonic.events"; la clave de enrutado es el campo "tipo" del sobre.
# - Mensajes persistentes y con confirmación del broker (publisher confirms).
# - Sin RABBITMQ_URL (tests, desarrollo sin Docker) los eventos solo se escriben en el log.
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from config.errores import correlation_id_actual
from config.settings import NOMBRE_SERVICIO

log = logging.getLogger("eventos")

EXCHANGE = "subsonic.events"
_local = threading.local()  # una conexión por hilo: pika no se puede compartir entre hilos


def rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", "")


def construir_sobre(tipo: str, datos: dict, version: int = 1) -> dict:
    return {
        "id_evento": str(uuid.uuid4()),
        "tipo": tipo,
        "version": version,
        "origen": NOMBRE_SERVICIO,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id_actual.get() or str(uuid.uuid4()),
        "datos": datos,
    }


def _canal():
    import pika
    canal = getattr(_local, "canal", None)
    if canal is None or canal.is_closed or canal.connection.is_closed:
        conexion = pika.BlockingConnection(pika.URLParameters(rabbitmq_url()))
        canal = conexion.channel()
        canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        canal.confirm_delivery()
        _local.canal = canal
    return canal


def publicar(tipo: str, datos: dict) -> dict:
    sobre = construir_sobre(tipo, datos)
    texto = json.dumps(sobre, default=str, ensure_ascii=False)
    if not rabbitmq_url():
        log.info("Evento publicado (sin RabbitMQ) %s", texto)
        return sobre

    import pika
    propiedades = pika.BasicProperties(content_type="application/json", delivery_mode=2, type=tipo,
                                       message_id=sobre["id_evento"], correlation_id=sobre["correlation_id"])
    # Dos intentos: si la conexión del hilo se cerró (reinicio del broker, heartbeat), se abre otra
    for intento in (1, 2):
        try:
            _canal().basic_publish(EXCHANGE, tipo, texto.encode(), propiedades)
            log.info("Evento publicado %s %s", tipo, sobre["id_evento"])
            return sobre
        except Exception as e:  # noqa: BLE001 - cualquier fallo del broker
            _local.canal = None
            log.warning("No se pudo publicar %s (intento %s): %s", tipo, intento, e)

    # La operación de negocio ya está guardada: no se deshace, pero el evento queda en el log
    # para poder reenviarlo. (Mejora futura: patrón outbox.)
    log.error("EVENTO NO PUBLICADO %s", texto)
    return sobre
