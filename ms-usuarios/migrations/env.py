"""Migraciones de usuarios_db; la URL procede de config/settings.py."""
from alembic import context
from sqlalchemy import create_engine, pool
from config.settings import DATABASE_URL
from model.models import Base

config = context.config
target_metadata = Base.metadata


def migrar(conexion):
    context.configure(connection=conexion, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrar(config.attributes["connection"])
else:
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    try:
        with engine.connect() as conexion:
            migrar(conexion)
    finally:
        engine.dispose()
