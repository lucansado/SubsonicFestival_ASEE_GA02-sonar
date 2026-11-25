# ms-usuarios/config/errores.py
# Formato común de errores de la ASEE: { codigo, mensaje, detalles, correlation_id }
import uuid
from contextvars import ContextVar
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# correlation-id de la petición en curso (se propaga también en los eventos)
correlation_id_actual: ContextVar[str] = ContextVar("correlation_id", default="")


class ErrorApi(Exception):
    """Error de negocio que se traduce a una respuesta HTTP con el formato común."""

    def __init__(self, status: int, codigo: str, mensaje: str, detalles: dict | None = None,
                 cabeceras: dict | None = None):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles
        self.cabeceras = cabeceras  # p. ej. {"Retry-After": "5"} en un 503


def _respuesta(status: int, codigo: str, mensaje: str, detalles=None, cabeceras=None) -> JSONResponse:
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "correlation_id": correlation_id_actual.get() or None}
    if detalles:
        cuerpo["detalles"] = detalles
    return JSONResponse(status_code=status, content=jsonable_encoder(cuerpo), headers=cabeceras)


def configurar_errores(app: FastAPI):
    @app.middleware("http")
    async def correlation_id(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        correlation_id_actual.set(cid)
        respuesta = await call_next(request)
        respuesta.headers["X-Correlation-Id"] = cid
        return respuesta

    @app.exception_handler(ErrorApi)
    async def error_api(_: Request, exc: ErrorApi):
        return _respuesta(exc.status, exc.codigo, exc.mensaje, exc.detalles, exc.cabeceras)

    @app.exception_handler(RequestValidationError)
    async def error_validacion(_: Request, exc: RequestValidationError):
        # La especificación usa 400 (no el 422 por defecto de FastAPI)
        return _respuesta(400, "PETICION_NO_VALIDA", "Datos de entrada no válidos", {"errores": exc.errors()})

    @app.exception_handler(StarletteHTTPException)
    async def error_http(_: Request, exc: StarletteHTTPException):
        codigos = {401: "NO_AUTENTICADO", 403: "SIN_PERMISO", 404: "NO_ENCONTRADO", 405: "METODO_NO_PERMITIDO"}
        return _respuesta(exc.status_code, codigos.get(exc.status_code, "ERROR"), str(exc.detail))
