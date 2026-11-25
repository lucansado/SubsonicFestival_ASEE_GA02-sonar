# ms-usuarios/main.py
# Punto de entrada del microservicio Usuarios
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.cors_config import configurar_cors
from config.database import crear_tablas
from config.errores import configurar_errores
from config.settings import NOMBRE_SERVICIO, PREFIJO_API, PUERTO
from controller import entradas_controller, usuarios_controller
from eventos.manejadores import consumidor
from service.firebase_auth import inicializar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    crear_tablas()
    inicializar()
    hilo = consumidor.iniciar()
    try:
        yield
    finally:
        consumidor.detener()
        if hilo is not None:
            hilo.join(timeout=10)


app = FastAPI(
    title="Subsonic Festival - ms-usuarios",
    version="1.0.0",
    description="Perfiles, roles, proveedores, entradas con QR firmado, favoritos y notificaciones.",
    lifespan=lifespan,
)

configurar_cors(app)
configurar_errores(app)

app.include_router(usuarios_controller.router, prefix=PREFIJO_API)
app.include_router(entradas_controller.router, prefix=PREFIJO_API)


@app.get("/salud", tags=["Infraestructura"], summary="Comprobación de vida (gateway / Docker)")
def salud():
    return {"servicio": NOMBRE_SERVICIO, "estado": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=PUERTO, reload=True)
