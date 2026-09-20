from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modulos_juegos.modalidades import obtener
from app.modulos_juegos.motor import obtener_reglas
from app.modelos.juegos import PlantillaSorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/admin", tags=["config"])


class SistemaEditar(BaseModel):
    horarios: str | None = None
    semanal_horario: str | None = None
    semanal_dia_inicio: int | None = Field(default=None, ge=0, le=6)
    semanal_dia_fin: int | None = Field(default=None, ge=0, le=6)
    busqueda_inicio_min: int | None = Field(default=None, ge=0)
    busqueda_intervalo_min: int | None = Field(default=None, ge=1)
    busqueda_duracion_min: int | None = Field(default=None, ge=1)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)


class PlantillaCrear(BaseModel):
    nombre: str
    modalidad: str
    horario: str | None = None
    precio_jugada: float = Field(gt=0)
    pozo_base: float = Field(ge=0)
    casa_pct: float = Field(ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    premio_fijo: float | None = Field(default=None, gt=0)
    descripcion: str | None = None


# ---------- CONFIGURACION DE SISTEMA (horarios y busqueda) ----------

@router.get("/sistema")
def ver_sistema(sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))):
    reglas = obtener_reglas(sesion)
    return {
        "horarios": reglas.dict_horarios(),
        "semanal_horario": reglas.semanal_horario,
        "semanal_dia_inicio": reglas.semanal_dia_inicio,
        "semanal_dia_fin": reglas.semanal_dia_fin,
        "busqueda_inicio_min": reglas.busqueda_inicio_min,
        "busqueda_intervalo_min": reglas.busqueda_intervalo_min,
        "busqueda_duracion_min": reglas.busqueda_duracion_min,
        "vendedor_pct": reglas.vendedor_pct,
    }


@router.put("/sistema")
def editar_sistema(datos: SistemaEditar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    reglas = obtener_reglas(sesion)
    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(reglas, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "SISTEMA_EDITADO", detalle=str(datos.model_dump(exclude_none=True)), usuario=admin)
    sesion.commit()
    return {"ok": True}


# ---------- GUIAS GUARDADAS (plantillas de sorteo) ----------

@router.post("/plantillas")
def crear_plantilla(datos: PlantillaCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))):
    if obtener(datos.modalidad) is None:
        raise HTTPException(status_code=400, detail="Modalidad inexistente")
    plantilla = PlantillaSorteo(**datos.model_dump())
    sesion.add(plantilla)
    sesion.commit()
    sesion.refresh(plantilla)
    auditoria.registrar(sesion, "PLANTILLA_CREADA", detalle=plantilla.nombre, usuario=admin)
    sesion.commit()
    return {"id": plantilla.id, "nombre": plantilla.nombre}


@router.get("/plantillas")
def listar_plantillas(sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))):
    ps = sesion.query(PlantillaSorteo).order_by(PlantillaSorteo.nombre).all()
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "modalidad": p.modalidad,
            "horario": p.horario,
            "precio_jugada": p.precio_jugada,
            "pozo_base": p.pozo_base,
            "casa_pct": p.casa_pct,
            "vendedor_pct": p.vendedor_pct,
            "premio_fijo": p.premio_fijo,
            "descripcion": p.descripcion,
        }
        for p in ps
    ]


@router.delete("/plantillas/{plantilla_id}")
def borrar_plantilla(plantilla_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))):
    p = sesion.get(PlantillaSorteo, plantilla_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    nombre = p.nombre
    sesion.delete(p)
    sesion.commit()
    auditoria.registrar(sesion, "PLANTILLA_BORRADA", detalle=nombre, usuario=admin)
    sesion.commit()
    return {"ok": True}
