# ms-usuarios/tests/conftest.py
# Los tests usan una BD SQLite temporal para no depender de Docker
import os
import sys
import tempfile
from pathlib import Path

import pytest

_bd = Path(tempfile.mkdtemp()) / "usuarios_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_bd.as_posix()}"
os.environ["FIREBASE_CREDENCIALES"] = ""
os.environ["RABBITMQ_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from config.database import engine, crear_tablas, SessionLocal  # noqa: E402
from main import app  # noqa: E402
from model.models import Base  # noqa: E402

ADMIN = {"X-User-Id": "admin-1", "X-User-Rol": "ADMIN"}  # el rol puede venir en mayúsculas
CLIENTE = {"X-User-Id": "cliente-1", "X-User-Rol": "cliente"}
OTRO_CLIENTE = {"X-User-Id": "cliente-2", "X-User-Rol": "cliente"}


@pytest.fixture
def bd_limpia():
    crear_tablas()
    with engine.begin() as conexion:
        for tabla in reversed(Base.metadata.sorted_tables):
            conexion.execute(tabla.delete())


@pytest.fixture
def db(bd_limpia):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def cliente_http(bd_limpia):
    with TestClient(app) as c:
        yield c
STAFF = {"X-User-Id": "staff-1", "X-User-Rol": "STAFF"}
