from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RevendedorCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    telefono: str | None = None
    codigo: str = Field(max_length=10)
    comision_pct: float = Field(ge=0, le=100)
    datos_transferencia: str | None = None


class RevendedorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario: str
    nombre: str
    telefono: str | None
    codigo: str | None
    comision_pct: float | None
    datos_transferencia: str | None
    activo: bool


class RevendedorEditar(BaseModel):
    nombre: str | None = None
    telefono: str | None = None
    codigo: str | None = None
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    datos_transferencia: str | None = None
    activo: bool | None = None


class AdminCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    permisos: list[str] = []


class AdminOut(BaseModel):
    id: int
    usuario: str
    nombre: str
    permisos: list[str]
    activo: bool


class AdminEditar(BaseModel):
    nombre: str | None = None
    permisos: list[str] | None = None
    activo: bool | None = None


class DosFaIniciarOut(BaseModel):
    secreto: str
    uri: str


class DosFaConfirmar(BaseModel):
    secreto: str
    codigo: str


class PasswordCambiar(BaseModel):
    actual: str
    nueva: str = Field(min_length=8)


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: datetime
    nombre_usuario: str | None
    accion: str
    detalle: str | None
