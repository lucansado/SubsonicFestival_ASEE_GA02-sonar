# ms-usuarios/config/cors_config.py
# En producción el CORS lo aplica el API Gateway; aquí se permite todo para desarrollo local.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def configurar_cors(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count", "Location", "X-Correlation-Id"],
    )
