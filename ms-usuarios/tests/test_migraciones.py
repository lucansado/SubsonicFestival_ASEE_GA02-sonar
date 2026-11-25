import os
import subprocess
import sys

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from config.settings import BASE_DIR
from model.models import Base


def configuracion(conexion):
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.attributes["connection"] = conexion
    return config


def test_upgrade_esquema_completo_y_downgrade(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migraciones.db').as_posix()}")
    try:
        with engine.begin() as conexion:
            config = configuracion(conexion)
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            inspector = inspect(conexion)
            assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
            assert conexion.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            assert compare_metadata(MigrationContext.configure(conexion), Base.metadata) == []
            command.downgrade(config, "base")
            assert inspect(conexion).get_table_names() == ["alembic_version"]
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_adopcion_de_bd_semana_1_conserva_datos(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'antigua.db').as_posix()}")
    try:
        with engine.begin() as conexion:
            tablas_antiguas = [t for t in Base.metadata.sorted_tables if t.name != "eventos_procesados"]
            Base.metadata.create_all(conexion, tables=tablas_antiguas)
            conexion.execute(text("INSERT INTO usuarios (id, email, rol, activo, creado_en) "
                                  "VALUES ('uid', 'uid@test.com', 'CLIENTE', 1, '2026-10-26')"))
            config = configuracion(conexion)
            command.stamp(config, "0001")
            command.upgrade(config, "head")
            assert conexion.scalar(text("SELECT email FROM usuarios WHERE id = 'uid'")) == "uid@test.com"
            assert "eventos_procesados" in inspect(conexion).get_table_names()
            assert compare_metadata(MigrationContext.configure(conexion), Base.metadata) == []
    finally:
        engine.dispose()


def test_cli_lee_database_url_fuera_del_directorio_del_servicio(tmp_path):
    archivo = tmp_path / "url con espacios.db"
    entorno = os.environ | {"DATABASE_URL": f"sqlite:///{archivo.as_posix()}"}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BASE_DIR / "alembic.ini"), "upgrade", "head"],
        cwd=tmp_path, env=entorno, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert archivo.exists()


def test_sql_postgresql_incluye_jsonb_uuid_y_claves(tmp_path):
    entorno = os.environ | {"DATABASE_URL": "postgresql+psycopg://prueba:prueba@localhost/prueba"}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BASE_DIR / "alembic.ini"), "upgrade", "head", "--sql"],
        cwd=tmp_path, env=entorno, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    for fragmento in ("fcm_tokens JSONB", "artista_id UUID", "FOREIGN KEY(usuario_id)",
                      "CREATE INDEX ix_entradas_evento_id", "CREATE TABLE eventos_procesados"):
        assert fragmento in resultado.stdout
