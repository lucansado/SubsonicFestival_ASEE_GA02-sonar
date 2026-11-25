# ms-usuarios/model/models.py
# Tablas de usuarios_db (ver "Almacenamiento" en openapi.yaml)
from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# JSONB en PostgreSQL; JSON genérico en los tests con SQLite
ListaJSON = JSON().with_variant(JSONB(), "postgresql")


def ahora():
    return datetime.now(timezone.utc)


class EventoProcesado(Base):
    """Recepciones completadas: una redelivery con el mismo ID no repite los avisos."""
    __tablename__ = "eventos_procesados"

    id_evento = Column(String(36), primary_key=True)
    tipo = Column(String(100), nullable=False)
    procesado_en = Column(DateTime(timezone=True), nullable=False, default=ahora)


# TABLA USUARIOS: perfil común de todos los usuarios registrados
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String(128), primary_key=True)  # UID de Firebase
    email = Column(String(255), unique=True, nullable=False)
    nombre = Column(String(100))
    apellidos = Column(String(255))
    telefono = Column(String(20))
    direccion = Column(String(255))
    rol = Column(String(20), nullable=False)  # CLIENTE, PROVEEDOR, ADMIN o STAFF
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora)
    eliminado_en = Column(DateTime(timezone=True), nullable=True)  # cuenta borrada y datos anonimizados (RGPD)

    proveedor = relationship("Proveedor", uselist=False, back_populates="usuario", cascade="all, delete-orphan")


# TABLA PROVEEDORES: datos adicionales de los proveedores
class Proveedor(Base):
    __tablename__ = "proveedores"

    usuario_id = Column(String(128), ForeignKey("usuarios.id"), primary_key=True)
    nombre_comercial = Column(String(200))
    cif = Column(String(20))
    tipo_servicio = Column(String(100))
    descripcion_servicio = Column(Text)
    validado = Column(Boolean, nullable=False, default=False)

    usuario = relationship("Usuario", back_populates="proveedor")


# TABLA ENTRADAS: entradas compradas por los clientes
class Entrada(Base):
    __tablename__ = "entradas"

    id = Column(String(50), primary_key=True)  # ej: "entrada-abc12345"
    usuario_id = Column(String(128), ForeignKey("usuarios.id"), nullable=False, index=True)
    evento_id = Column(String(100), nullable=False, index=True)  # ref. ms-espacios
    # Copia de los datos del evento en el momento de la compra
    evento_titulo = Column(String(200))
    evento_fechas = Column(String(100))  # ej: "18 – 27 Julio 2026"
    evento_fecha_inicio = Column(Date)  # para saber si el evento ya ha empezado
    evento_fecha_fin = Column(Date)
    tipo_pase = Column(String(20), nullable=False)  # DAY, WEEKEND o VIP
    precio_pagado = Column(Numeric(8, 2), nullable=False)
    estado = Column(String(30), nullable=False, default="ACTIVA")
    codigo_qr = Column(String(255), nullable=False)
    reserva_id = Column(Uuid)
    pago_ref = Column(String(100))
    motivo_cancelacion = Column(Text)
    comprada_en = Column(DateTime(timezone=True), nullable=False, default=ahora)
    usada_en = Column(DateTime(timezone=True))

    usuario = relationship("Usuario")


# TABLA ARTISTAS_FAVORITOS: artistas marcados por los clientes
class ArtistaFavorito(Base):
    __tablename__ = "artistas_favoritos"

    usuario_id = Column(String(128), ForeignKey("usuarios.id"), primary_key=True)
    artista_id = Column(Uuid, primary_key=True)  # ref. ms-escaleta
    artista_nombre = Column(String(255))
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora)


# TABLA PREFERENCIAS_NOTIFICACION: canales de notificación
class PreferenciasNotificacion(Base):
    __tablename__ = "preferencias_notificacion"

    usuario_id = Column(String(128), ForeignKey("usuarios.id"), primary_key=True)
    push = Column(Boolean, nullable=False, default=True)
    email = Column(Boolean, nullable=False, default=True)
    fcm_tokens = Column(ListaJSON, nullable=False, default=list)
