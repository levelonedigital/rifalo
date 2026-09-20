from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.core.security import hash_password
from app.modulos_juegos.jugadas_core import crear_jugada
from app.modulos_juegos.modalidades import obtener
from app.modulos_juegos.motor import aprobar_jugada, obtener_reglas
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/vendedor", tags=["vendedor"])

vendedor_dep = Depends(requerir_rol(RolUsuario.VENDEDOR))


class RevendedorCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    codigo: str = Field(max_length=10)
    comision_pct: float = Field(ge=0, le=100)
    telefono: str | None = None


class RevendedorEditar(BaseModel):
    nombre: str | None = None
    telefono: str | None = None
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    activo: bool | None = None


class JugadaCrear(BaseModel):
    sorteo_id: int
    numeros: list[int]
    jugador_nombre: str | None = None


def _comision_propia(vendedor: Usuario, reglas) -> float:
    return vendedor.comision_pct if vendedor.comision_pct is not None else reglas.vendedor_pct


def _mio(sesion: Session, jugada_id: int, vendedor: Usuario) -> Jugada:
    jugada = sesion.get(Jugada, jugada_id)
    if jugada is None or jugada.vendedor_id != vendedor.id:
        raise HTTPException(status_code=404, detail="Jugada no encontrada en tu linea")
    return jugada


def _sorteo_out(s: Sorteo):
    modalidad = obtener(s.modalidad)
    return {
        "id": s.id,
        "modalidad": s.modalidad,
        "nombre_modalidad": modalidad.nombre if modalidad else s.modalidad,
        "reglas": modalidad.resumen_reglas if modalidad else "",
        "cantidad_numeros": modalidad.cantidad_numeros if modalidad else 0,
        "horario": s.horario,
        "fecha": s.fecha.isoformat(),
        "pozo": s.pozo_actual,
        "precio_jugada": s.precio_jugada,
        "solo_participantes": s.solo_participantes,
        "reprogramando": s.estado == EstadoSorteo.REPROGRAMANDO,
    }


# ---------- REVENDEDORES PROPIOS ----------

@router.post("/revendedores")
def crear_revendedor(datos: RevendedorCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    reglas = obtener_reglas(sesion)
    if datos.comision_pct > _comision_propia(vendedor, reglas):
        raise HTTPException(status_code=400, detail="La comision del revendedor no puede superar la tuya")
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if sesion.query(Usuario).filter(Usuario.codigo == datos.codigo.upper()).first():
        raise HTTPException(status_code=400, detail="El codigo ya existe")
    rev = Usuario(
        usuario=datos.usuario,
        password_hash=hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.REVENDEDOR,
        codigo=datos.codigo.upper(),
        comision_pct=datos.comision_pct,
        padre_id=vendedor.id,
        activo=True,
    )
    sesion.add(rev)
    sesion.commit()
    auditoria.registrar(sesion, "REVENDEDOR_CREADO", detalle=f"{rev.usuario} bajo {vendedor.usuario}", usuario=vendedor)
    sesion.commit()
    return {"id": rev.id, "usuario": rev.usuario, "codigo": rev.codigo, "comision_pct": rev.comision_pct}


@router.get("/revendedores")
def listar_revendedores(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    revs = sesion.query(Usuario).filter(Usuario.padre_id == vendedor.id, Usuario.rol == RolUsuario.REVENDEDOR).all()
    return [
        {"id": r.id, "usuario": r.usuario, "nombre": r.nombre, "codigo": r.codigo, "comision_pct": r.comision_pct, "activo": r.activo}
        for r in revs
    ]


@router.put("/revendedores/{revendedor_id}")
def editar_revendedor(revendedor_id: int, datos: RevendedorEditar, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = sesion.get(Usuario, revendedor_id)
    if rev is None or rev.padre_id != vendedor.id or rev.rol != RolUsuario.REVENDEDOR:
        raise HTTPException(status_code=404, detail="Revendedor no encontrado en tu linea")
    reglas = obtener_reglas(sesion)
    if datos.comision_pct is not None:
        if datos.comision_pct > _comision_propia(vendedor, reglas):
            raise HTTPException(status_code=400, detail="La comision no puede superar la tuya")
        rev.comision_pct = datos.comision_pct
    if datos.nombre is not None:
        rev.nombre = datos.nombre
    if datos.telefono is not None:
        rev.telefono = datos.telefono
    if datos.activo is not None:
        rev.activo = datos.activo
    sesion.commit()
    auditoria.registrar(sesion, "REVENDEDOR_EDITADO", detalle=rev.usuario, usuario=vendedor)
    sesion.commit()
    return {"id": rev.id, "usuario": rev.usuario, "comision_pct": rev.comision_pct, "activo": rev.activo}


# ---------- JUGADORES PROPIOS ----------

@router.get("/jugadores")
def listar_jugadores(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadores = sesion.query(Usuario).filter(Usuario.padre_id == vendedor.id, Usuario.rol == RolUsuario.JUGADOR).all()
    return [{"id": j.id, "usuario": j.usuario, "nombre": j.nombre, "activo": j.activo} for j in jugadores]


# ---------- JUGADAS ----------

@router.get("/sorteos")
def sorteos_abiertos(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado.in_([EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO]))
        .order_by(Sorteo.fecha)
        .all()
    )
    return [_sorteo_out(s) for s in sorteos]


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    try:
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, jugador_nombre=datos.jugador_nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": jugada.id, "numeros": jugada.numeros, "precio": jugada.precio, "estado": jugada.estado.value}


@router.get("/jugadas/pendientes")
def pendientes(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.vendedor_id == vendedor.id, Jugada.estado == EstadoJugada.PENDIENTE)
        .order_by(Jugada.creada_en)
        .limit(300)
        .all()
    )
    return [
        {
            "id": j.id,
            "sorteo_id": j.sorteo_id,
            "numeros": j.numeros,
            "precio": j.precio,
            "jugador_nombre": j.jugador_nombre,
            "revendedor_id": j.revendedor_id,
            "jugador_id": j.jugador_id,
        }
        for j in jugadas
    ]


@router.post("/jugadas/{jugada_id}/aprobar")
def aprobar(jugada_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugada = _mio(sesion, jugada_id, vendedor)
    if jugada.estado != EstadoJugada.PENDIENTE:
        raise HTTPException(status_code=400, detail="La jugada no esta pendiente")
    reglas = obtener_reglas(sesion)
    aprobar_jugada(sesion, jugada, reglas)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADA_APROBADA", detalle=f"jugada={jugada.id}", usuario=vendedor)
    sesion.commit()
    return {"id": jugada.id, "estado": jugada.estado.value}


@router.post("/jugadas/{jugada_id}/rechazar")
def rechazar(jugada_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugada = _mio(sesion, jugada_id, vendedor)
    if jugada.estado != EstadoJugada.PENDIENTE:
        raise HTTPException(status_code=400, detail="La jugada no esta pendiente")
    jugada.estado = EstadoJugada.RECHAZADA
    sesion.commit()
    auditoria.registrar(sesion, "JUGADA_RECHAZADA", detalle=f"jugada={jugada.id}", usuario=vendedor)
    sesion.commit()
    return {"id": jugada.id, "estado": jugada.estado.value}


@router.get("/jugadas")
def historial(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.vendedor_id == vendedor.id)
        .order_by(Jugada.creada_en.desc())
        .limit(300)
        .all()
    )
    return [
        {"id": j.id, "sorteo_id": j.sorteo_id, "numeros": j.numeros, "precio": j.precio, "estado": j.estado.value, "premio": j.premio, "mi_comision": j.monto_vendedor}
        for j in jugadas
    ]


@router.get("/resumen")
def resumen(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadas = sesion.query(Jugada).filter(Jugada.vendedor_id == vendedor.id, Jugada.estado == EstadoJugada.APROBADA).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "mi_comision": round(sum(j.monto_vendedor or 0 for j in jugadas), 2),
        "comision_revendedores": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
    }
