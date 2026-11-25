import json
from unittest.mock import Mock
import pika
import pytest
from config.errores import correlation_id_actual
from eventos.consumidor import Consumidor
from eventos.manejadores import CLAVES
from eventos import publicador


def mensaje():
    return json.dumps({"tipo": "prueba", "id_evento": "id", "correlation_id": "cid", "datos": {}}).encode()


def test_declaracion_cola_y_confirmacion_reintentos():
    canal = Mock()
    Consumidor("ms-usuarios", CLAVES, Mock()).declarar(canal)
    canal.queue_declare.assert_called_once_with("ms-usuarios", durable=True,
                                               arguments={"x-dead-letter-exchange": "subsonic.dlx"})
    assert {c.kwargs["routing_key"] for c in canal.queue_bind.call_args_list} == set(CLAVES)
    assert len(CLAVES) == 11
    canal.confirm_delivery.assert_called_once()


def test_ack_solo_despues_del_manejador_y_propaga_correlacion():
    canal = Mock()
    previo = correlation_id_actual.get()

    def manejar(sobre):
        assert sobre["tipo"] == "prueba"
        assert correlation_id_actual.get() == "cid"
        canal.basic_ack.assert_not_called()

    Consumidor("cola", [], manejar).procesar_mensaje(canal, 7, pika.BasicProperties(), mensaje())
    canal.basic_ack.assert_called_once_with(7)
    assert correlation_id_actual.get() == previo


@pytest.mark.parametrize("intento", [0, 1, 2, 3])
def test_tres_reintentos_y_despues_dlq(intento):
    canal, manejar = Mock(), Mock(side_effect=RuntimeError("fallo"))
    propiedades = pika.BasicProperties(headers={"x-reintentos": intento}, message_id="id", correlation_id="cid")
    Consumidor("cola", [], manejar).procesar_mensaje(canal, 7, propiedades, mensaje())
    if intento < 3:
        args = canal.basic_publish.call_args
        assert args.args[:3] == ("", "cola", mensaje())
        assert args.args[3].headers == {"x-reintentos": intento + 1}
        assert args.args[3].delivery_mode == 2
        assert args.args[3].message_id == "id" and args.args[3].correlation_id == "cid"
        assert args.kwargs["mandatory"] is True
        canal.basic_ack.assert_called_once_with(7)
        canal.basic_nack.assert_not_called()
    else:
        canal.basic_publish.assert_not_called()
        canal.basic_ack.assert_not_called()
        canal.basic_nack.assert_called_once_with(7, requeue=False)


def test_no_ack_si_falla_republicar_el_reintento():
    canal = Mock()
    canal.basic_publish.side_effect = RuntimeError("broker caído")
    consumidor = Consumidor("cola", [], Mock(side_effect=RuntimeError("fallo")))
    with pytest.raises(RuntimeError):
        consumidor.procesar_mensaje(canal, 7, pika.BasicProperties(), mensaje())
    canal.basic_ack.assert_not_called()


@pytest.mark.parametrize("cuerpo", [b"invalid", b"null", b"[]", b"123", b"\xff"])
def test_json_invalido_va_a_dlq(cuerpo):
    canal, manejar = Mock(), Mock()
    Consumidor("cola", [], manejar).procesar_mensaje(canal, 7, pika.BasicProperties(), cuerpo)
    manejar.assert_not_called()
    canal.basic_nack.assert_called_once_with(7, requeue=False)


@pytest.mark.parametrize("valor", ["incorrecto", -1, None])
def test_contador_invalido_va_a_dlq(valor):
    canal = Mock()
    consumidor = Consumidor("cola", [], Mock(side_effect=RuntimeError("fallo")))
    consumidor.procesar_mensaje(canal, 7, pika.BasicProperties(headers={"x-reintentos": valor}), mensaje())
    canal.basic_nack.assert_called_once_with(7, requeue=False)


def test_sin_url_no_arranca_y_publica_solo_log(monkeypatch, caplog):
    monkeypatch.setenv("RABBITMQ_URL", "")
    conexion = Mock()
    monkeypatch.setattr(pika, "BlockingConnection", conexion)
    with caplog.at_level("INFO"):
        publicado = publicador.publicar("usuarios.prueba", {"valor": 1})
        assert Consumidor("cola", [], Mock()).iniciar() is None
    assert publicado["datos"] == {"valor": 1} and publicado["origen"] == "ms-usuarios"
    assert "sin RabbitMQ" in caplog.text
    conexion.assert_not_called()


def test_publicacion_persistente_y_confirmada(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://localhost")
    canal = Mock()
    conexion = Mock()
    conexion.channel.return_value = canal
    monkeypatch.setattr(pika, "BlockingConnection", Mock(return_value=conexion))
    monkeypatch.setattr(publicador._local, "canal", None, raising=False)
    publicado = publicador.publicar("usuarios.entrada.comprada", {"entrada_id": "e1"})
    canal.confirm_delivery.assert_called_once()
    args = canal.basic_publish.call_args.args
    assert args[:2] == ("subsonic.events", "usuarios.entrada.comprada")
    assert json.loads(args[2]) == publicado
    assert args[3].delivery_mode == 2 and args[3].message_id == publicado["id_evento"]
