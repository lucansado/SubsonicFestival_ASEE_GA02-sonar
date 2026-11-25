# ms-usuarios/model/dto/usuario_dto.py
# Esquemas Usuario, DatosProveedor, RegistroEntrada, PerfilCambio, PreferenciasNotificacion de openapi.yaml
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Rol(str, Enum):
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"
    ADMIN = "ADMIN"
    STAFF = "STAFF"


class RolRegistro(str, Enum):
    """Al registrarse solo se puede ser cliente o proveedor."""
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"


class DatosProveedorEntradaDTO(BaseModel):
    nombre_comercial: str | None = None
    cif: str | None = Field(default=None, max_length=20)
    tipo_servicio: str | None = None
    descripcion_servicio: str | None = None


class DatosProveedorDTO(DatosProveedorEntradaDTO):
    model_config = ConfigDict(from_attributes=True)

    validado: bool = False  # solo lectura: lo cambia un administrador


class UsuarioDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    nombre: str | None = None
    apellidos: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    rol: Rol
    activo: bool
    creado_en: datetime | None = None
    proveedor: DatosProveedorDTO | None = None


class RegistroEntradaDTO(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    apellidos: str | None = None
    telefono: str | None = Field(default=None, max_length=20)
    direccion: str | None = None
    rol: RolRegistro
    proveedor: DatosProveedorEntradaDTO | None = None


class PerfilCambioDTO(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    apellidos: str | None = None
    telefono: str | None = Field(default=None, max_length=20)
    direccion: str | None = None
    activo: bool | None = None
    proveedor: DatosProveedorEntradaDTO | None = None

    @model_validator(mode="after")
    def al_menos_un_campo(self):
        if not self.model_fields_set:
            raise ValueError("Hay que enviar al menos un campo")
        return self


class CambioUsuarioAdminDTO(BaseModel):
    rol: Rol | None = None
    activo: bool | None = None

    @model_validator(mode="after")
    def al_menos_un_campo(self):
        if self.rol is None and self.activo is None:
            raise ValueError("Hay que enviar rol o activo")
        return self


class ValidacionProveedorDTO(BaseModel):
    validado: bool


class PreferenciasNotificacionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    push: bool
    email: bool


class Plataforma(str, Enum):
    WEB = "WEB"
    ANDROID = "ANDROID"
    IOS = "IOS"


class DispositivoEntradaDTO(BaseModel):
    fcm_token: str = Field(min_length=1)
    plataforma: Plataforma | None = None
