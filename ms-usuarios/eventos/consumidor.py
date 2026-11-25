# eventos/consumidor.py  (plantilla común: rama infra, carpeta plantilla-mensajeria)
# Consumidor de eventos de RabbitMQ para un microservicio.
# - Una cola duradera por servicio (p. ej. "ms-espacios"), enlazada a subsonic.events con las claves
#   que le interesan ("usuarios.entrada.*", "#"…).
# - ack solo cuando el manejador termina bien. Si falla, se reintenta hasta 3 veces; después el
#   mensaje va a la cola de mensajes fallidos subsonic.dlq (dead letter exchange subsonic.dlx).
# - Se ejecuta en un hilo aparte y se reconecta solo si el broker se reinicia.
# - Sin RABBITMQ_URL no arranca (tests, desarrollo sin Docker).
import json
import logging
import threading
from typing import Callable
from config.errores import correlation_id_actual
from eventos.publicador import EXCHANGE, rabbitmq_url

log = logging.getLogger("consumidor")

DLX = "subsonic.dlx"
MAX_REINTENTOS = 3
SEGUNDOS_RECONEXION = 5


class Consumidor:
    def __init__(self, cola: str, claves: list[str], manejador: Callable[[dict], None],
                 max_reintentos: int = MAX_REINTENTOS):
        self.cola = cola
        self.claves = claves
        self.manejador = manejador  # recibe el sobre completo: {"id_evento", "tipo", "datos", …}
        self.max_reintentos = max_reintentos
        self._parar = threading.Event()
        self._conexion = None

    # ── Arranque y parada (desde el lifespan de main.py) ─────

    def iniciar(self) -> threading.Thread | None:
        if not rabbitmq_url():
            log.info("Sin RABBITMQ_URL: el consumidor %s no se inicia", self.cola)
            return None
        self._parar.clear()
        hilo = threading.Thread(target=self._bucle, name=f"consumidor-{self.cola}", daemon=True)
        hilo.start()
        return hilo

    def detener(self) -> None:
        self._parar.set()
        conexion = self._conexion
        if conexion is not None and conexion.is_open:
            import pika
            try:
                conexion.add_callback_threadsafe(conexion.close)
            except pika.exceptions.ConnectionWrongStateError:
                pass  # el broker ya cerró la conexión

    def _bucle(self) -> None:
        import pika
        while not self._parar.is_set():
            try:
                self._conexion = pika.BlockingConnection(pika.URLParameters(rabbitmq_url()))
                canal = self._conexion.channel()
                self.declarar(canal)
                canal.basic_qos(prefetch_count=10)
                canal.basic_consume(self.cola, self._al_recibir)
                log.info("Consumidor %s escuchando %s", self.cola, self.claves)
                canal.start_consuming()
            except Exception as e:  # noqa: BLE001 - broker caído, conexión cerrada…
                if self._parar.is_set():
                    break
                log.warning("Consumidor %s desconectado (%s); reintento en %s s", self.cola, e, SEGUNDOS_RECONEXION)
                self._parar.wait(SEGUNDOS_RECONEXION)
            finally:
                conexion, self._conexion = self._conexion, None
                if conexion is not None and conexion.is_open:
                    try:
                        conexion.close()
                    except pika.exceptions.AMQPError:
                        log.warning("La conexión del consumidor ya no responde al cerrar")

    def declarar(self, canal) -> None:
        canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        canal.queue_declare(self.cola, durable=True, arguments={"x-dead-letter-exchange": DLX})
        for clave in self.claves:
            canal.queue_bind(self.cola, EXCHANGE, routing_key=clave)
        canal.confirm_delivery()  # no confirmar el original hasta asegurar la copia del reintento

    def _al_recibir(self, canal, metodo, propiedades, cuerpo) -> None:
        self.procesar_mensaje(canal, metodo.delivery_tag, propiedades, cuerpo)

    # ── Un mensaje (separado para poder probarlo sin broker) ─

    def procesar_mensaje(self, canal, etiqueta, propiedades, cuerpo: bytes) -> None:
        try:
            sobre = json.loads(cuerpo)
            if not isinstance(sobre, dict):
                raise ValueError("El sobre debe ser un objeto")
        except ValueError:
            log.error("Mensaje ilegible en %s: se manda a la DLQ", self.cola)
            canal.basic_nack(etiqueta, requeue=False)
            return

        token = correlation_id_actual.set(sobre.get("correlation_id") or "")
        try:
            self.manejador(sobre)
            canal.basic_ack(etiqueta)
            return
        except Exception:  # noqa: BLE001 - el error del manejador decide el reintento
            log.exception("Error procesando %s %s en %s", sobre.get("tipo"), sobre.get("id_evento"), self.cola)
        finally:
            correlation_id_actual.reset(token)

        cabeceras = dict(getattr(propiedades, "headers", None) or {})
        try:
            reintentos = int(cabeceras.get("x-reintentos", 0))
            if reintentos < 0:
                raise ValueError("Contador negativo")
        except (TypeError, ValueError):
            canal.basic_nack(etiqueta, requeue=False)
            return
        if reintentos < self.max_reintentos:
            import pika
            cabeceras["x-reintentos"] = reintentos + 1
            nuevas = pika.BasicProperties(content_type="application/json", delivery_mode=2, headers=cabeceras,
                                          type=getattr(propiedades, "type", None),
                                          message_id=getattr(propiedades, "message_id", None),
                                          correlation_id=getattr(propiedades, "correlation_id", None))
            # Se vuelve a poner al final de la propia cola y se confirma el original
            canal.basic_publish("", self.cola, cuerpo, nuevas, mandatory=True)
            canal.basic_ack(etiqueta)
            log.warning("Reintento %s/%s de %s", reintentos + 1, self.max_reintentos, sobre.get("id_evento"))
        else:
            canal.basic_nack(etiqueta, requeue=False)  # -> subsonic.dlx -> subsonic.dlq
            log.error("Agotados los reintentos de %s: enviado a subsonic.dlq", sobre.get("id_evento"))
