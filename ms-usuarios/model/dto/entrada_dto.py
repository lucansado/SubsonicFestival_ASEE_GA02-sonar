# ms-usuarios/model/dto/entrada_dto.py
# Esquemas Entrada, CompraEntrada, Validacion y Favorito de openapi.yaml
from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TipoPase(str, Enum):
    DAY = "DAY"
    WEEKEND = "WEEKEND"
    VIP = "VIP"


class EstadoEntrada(str, Enum):
    ACTIVA = "ACTIVA"
    CANCELACION_SOLICITADA = "CANCELACION_SOLICITADA"
    CANCELADA = "CANCELADA"
    USADA = "USADA"


class ResolucionCancelacion(str, Enum):
    CANCELADA = "CANCELADA"
    ACTIVA = "ACTIVA"


class CompraEntradaDTO(BaseModel):
    evento_id: str = Field(min_length=1)
    tipo_pase: TipoPase
    token_pago: str = Field(min_length=1)


class EntradaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    evento_id: str
    evento_titulo: str | None = None
    evento_fechas: str | None = None
    tipo_pase: TipoPase
    precio_pagado: float
    estado: EstadoEntrada
    codigo_qr: str
    motivo_cancelacion: str | None = None
    comprada_en: datetime
    usada_en: datetime | None = None


class SolicitudCancelacionDTO(BaseModel):
    motivo: str = Field(min_length=5)


class ResolucionCancelacionDTO(BaseModel):
    estado: ResolucionCancelacion


class ValidacionEntradaDTO(BaseModel):
    codigo_qr: str = Field(min_length=1)
    evento_id: str = Field(min_length=1)


class ValidacionDTO(BaseModel):
    entrada_id: str
    tipo_pase: TipoPase
    titular: str
    validada_en: datetime


class FavoritoEntradaDTO(BaseModel):
    artista_id: UUID


class FavoritoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artista_id: UUID
    artista_nombre: str | None = None
    creado_en: datetime
