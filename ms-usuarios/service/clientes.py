# ms-usuarios/service/clientes.py
# Llamadas síncronas a otros microservicios: timeout de 2 s y 3 reintentos (memoria, apartado 4).
# Si el servicio no responde se devuelve 503 con Retry-After para que el cliente reintente.
import logging
import httpx
from config.errores import ErrorApi, correlation_id_actual
from config.settings import ESCALETA_URL, ESPACIOS_URL, REINTENTOS, TIMEOUT_SEGUNDOS, TOKEN_SERVICIO

log = logging.getLogger("clientes")


def _no_disponible(servicio: str) -> ErrorApi:
    return ErrorApi(503, "SERVICIO_NO_DISPONIBLE", f"{servicio} no está disponible; inténtalo de nuevo",
                    cabeceras={"Retry-After": "5"})


def _peticion(servicio: str, metodo: str, url: str, **kwargs) -> httpx.Response:
    cabeceras = kwargs.pop("headers", {}) | {"X-Correlation-Id": correlation_id_actual.get() or ""}
    for intento in range(1, REINTENTOS + 1):
        try:
            respuesta = httpx.request(metodo, url, headers=cabeceras, timeout=TIMEOUT_SEGUNDOS, **kwargs)
            if respuesta.status_code < 500:
                return respuesta
            log.warning("%s respondió %s (intento %s/%s)", servicio, respuesta.status_code, intento, REINTENTOS)
        except httpx.HTTPError as e:
            log.warning("%s no responde: %s (intento %s/%s)", servicio, e, intento, REINTENTOS)
    raise _no_disponible(servicio)


def _error_remoto(respuesta: httpx.Response) -> ErrorApi:
    """Reenvía al cliente el error de negocio de otro servicio (404, 409…)."""
    try:
        cuerpo = respuesta.json()
        return ErrorApi(respuesta.status_code, cuerpo.get("codigo", "ERROR"), cuerpo.get("mensaje", ""))
    except ValueError:
        return ErrorApi(respuesta.status_code, "ERROR", respuesta.text)


# ── ms-espacios (rutas internas) ────────────────────────────

def reservar_aforo(evento_id: str, tipo_pase: str, usuario_id: str) -> dict:
    respuesta = _peticion(
        "ms-espacios", "POST", f"{ESPACIOS_URL}/internal/v1/eventos/{evento_id}/reservas-aforo",
        headers={"X-Service-Token": TOKEN_SERVICIO}, json={"tipo_pase": tipo_pase, "usuario_id": usuario_id},
    )
    if respuesta.status_code != 201:
        raise _error_remoto(respuesta)
    return respuesta.json()


def liberar_aforo(reserva_id: str) -> None:
    """Si falla no pasa nada grave: la reserva caduca sola a los 10 minutos."""
    try:
        _peticion("ms-espacios", "DELETE", f"{ESPACIOS_URL}/internal/v1/reservas-aforo/{reserva_id}",
                  headers={"X-Service-Token": TOKEN_SERVICIO})
    except ErrorApi:
        log.warning("No se pudo liberar la reserva %s; caducará sola", reserva_id)


# ── ms-escaleta (API pública) ───────────────────────────────

def nombre_artista(artista_id: str) -> str | None:
    """Nombre del artista para copiarlo en favoritos. None si ms-escaleta no responde
    (se completará al recibir escaleta.artista.actualizado)."""
    try:
        respuesta = _peticion("ms-escaleta", "GET", f"{ESCALETA_URL}/api/v1/artistas/{artista_id}")
    except ErrorApi:
        return None
    if respuesta.status_code == 404:
        raise ErrorApi(400, "ARTISTA_NO_VALIDO", f"No existe el artista {artista_id}")
    return respuesta.json().get("nombre") if respuesta.status_code == 200 else None
