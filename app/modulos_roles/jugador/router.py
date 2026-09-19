from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modulos_juegos.jugadas_core import crear_jugada
from app.modulos_juegos.motor import obtener_reglas
from app.modelos.juegos import EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/jugador", tags=["jugador"])

jug_dep = Depends(requerir_rol(RolUsuario.JUGADOR))


class JugadaCrear(BaseModel):
    sorteo_id: int
    numeros: list[int]


@router.get("/sorteos")
def sorteos_abiertos(sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    sorteos = sesion.query(Sorteo).filter(Sorteo.estado == EstadoSorteo.PROGRAMADO).order_by(Sorteo.fecha).all()
    return [
        {"id": s.id, "modulo": s.modulo.value, "horario": s.horario, "fecha": s.fecha.isoformat(), "pozo": s.pozo_actual, "solo_participantes": s.solo_participantes}
        for s in sorteos
    ]


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    vendedor = sesion.get(Usuario, jugador.padre_id) if jugador.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor no esta activo")
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    reglas = obtener_reglas(sesion)
    try:
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, reglas, jugador_id=jugador.id, jugador_nombre=jugador.nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": jugada.id, "numeros": jugada.numeros, "precio": jugada.precio, "estado": jugada.estado.value}


@router.get("/jugadas")
def mis_jugadas(sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.jugador_id == jugador.id)
        .order_by(Jugada.creada_en.desc())
        .limit(300)
        .all()
    )
    return [
        {"id": j.id, "sorteo_id": j.sorteo_id, "numeros": j.numeros, "precio": j.precio, "estado": j.estado.value, "premio": j.premio}
        for j in jugadas
    ]
