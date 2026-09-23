from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.config import Configuracion
from app.core.database import obtener_sesion
from app.core.dependencias import obtener_usuario_actual, requerir_rol
from app.core.security import hash_password
from app.modulos_juegos.modalidades import obtener
from app.modulos_juegos.motor import obtener_reglas
from app.modelos.auditoria import LogAuditoria
from app.modelos.juegos import Aviso, Jugada, PlantillaSorteo, ReglasSistema, Sorteo
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


class ResetConfirm(BaseModel):
    confirmacion: str


# ---------- CONFIGURACION DE SISTEMA ----------

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


# ---------- GUIAS GUARDADAS ----------

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


# ---------- AVISOS ----------

@router.get("/avisos")
def ver_avisos(sesion: Session = Depends(obtener_sesion), usuario: Usuario = Depends(obtener_usuario_actual)):
    es_admin = usuario.rol in (RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN)
    consulta = sesion.query(Aviso)
    if not es_admin:
        consulta = consulta.filter(Aviso.destino == "todos")
    avisos = consulta.order_by(Aviso.creado_en.desc()).limit(5).all()
    return [
        {"id": a.id, "texto": a.texto, "destino": a.destino, "creado_en": a.creado_en.isoformat()}
        for a in avisos
    ]


@router.delete("/avisos/{aviso_id}")
def borrar_aviso(aviso_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))):
    aviso = sesion.get(Aviso, aviso_id)
    if aviso is not None:
        sesion.delete(aviso)
        sesion.commit()
    return {"ok": True}


# ---------- RESET DE FABRICA (usa TRUNCATE con RESTART IDENTITY para reiniciar contadores) ----------

TABLAS_A_TRUNCAR = [
    "jugadas",
    "sorteos",
    "avisos",
    "plantillas_sorteo",
    "log_auditoria",
    "reglas_sistema",
    "usuarios",
]


@router.post("/reset-total")
def reset_total(datos: ResetConfirm, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    """Borra absolutamente todo y reinicia los contadores de IDs a 1."""
    if datos.confirmacion != "BORRAR TODO":
        raise HTTPException(status_code=400, detail="Confirmacion invalida: escribi BORRAR TODO")
    
    dialecto = sesion.bind.dialect.name
    if dialecto == "postgresql":
        # PostgreSQL: TRUNCATE con RESTART IDENTITY CASCADE
        nombres = ", ".join(TABLAS_A_TRUNCAR)
        sesion.execute(text(f"TRUNCATE {nombres} RESTART IDENTITY CASCADE"))
    else:
        # SQLite y otros: DELETE y reinicio manual
        for tabla in TABLAS_A_TRUNCAR:
            sesion.execute(text(f"DELETE FROM {tabla}"))
        # SQLite: reiniciar secuencias
        for tabla in TABLAS_A_TRUNCAR:
            try:
                sesion.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tabla}'"))
            except Exception:
                pass
    sesion.commit()
    
    # Recrear admin inicial
    admin_nuevo = Usuario(
        usuario=Configuracion.ADMIN_INICIAL_USUARIO,
        password_hash=hash_password(Configuracion.ADMIN_INICIAL_PASSWORD),
        nombre="Administrador Principal",
        rol=RolUsuario.ADMIN_PRINCIPAL,
        activo=True,
        requiere_2fa=False,
    )
    sesion.add(admin_nuevo)
    sesion.commit()
    
    # Recrear reglas de sistema
    obtener_reglas(sesion)
    sesion.commit()
    
    return {"ok": True, "detalle": "Base vacia, contadores en 1. Admin inicial recreado."}
