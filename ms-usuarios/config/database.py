# ms-usuarios/config/database.py
# Conexión a PostgreSQL (usuarios_db) mediante SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import DATABASE_URL
from alembic import command
from alembic.config import Config
from config.settings import BASE_DIR

# SQLite solo se usa en los tests (sin Docker); en local y en contenedor es PostgreSQL
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def crear_tablas():
    """Aplica las migraciones pendientes, también desde el script de datos de prueba."""
    configuracion = Config(str(BASE_DIR / "alembic.ini"))
    with engine.begin() as conexion:
        configuracion.attributes["connection"] = conexion
        command.upgrade(configuracion, "head")


def get_db():
    """Dependencia de FastAPI: una sesión por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
