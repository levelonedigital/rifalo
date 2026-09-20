from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modulos_juegos.jugadas_core import crear_jugada
from app.modulos_juegos.modalidades import obtener
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/jugador", tags=["jugador"])

jug_dep = Depends(requerir_rol(RolUsuario.JUGADOR))

ESTADOS_ACTIVAS = [EstadoJugada.PENDIENTE, EstadoJugada.APROBADA]


class JugadaCrear(BaseModel):
    sorteo_id: int
    numeros: list[int]


def _sorteo_out(s: Sorteo):
    modalidad = obtener(s.modalidad)
    return {
        "id": s.id,
        "modalidad": s.modalidad,
        "nombre_modalidad": modalidad.nombre if modalidad else s.modalidad,
        "reglas": modalidad.resumen_reglas if modalidad else "",
        "detalle": s.detalle,
        "cantidad_numeros": modalidad.cantidad_numeros if modalidad else 0,
        "horario": s.horario,
        "fecha": s.fecha.isoformat(),
        "pozo": s.pozo_actual,
        "precio_jugada": s.precio_jugada,
        "solo_participantes": s.solo_participantes,
        "reprogramando": s.estado == EstadoSorteo.REPROGRAMANDO,
        "imagen_url": s.imagen_url,
    }


def _coincidencias(sesion: Session, sorteo_id: int, numeros_clave: str) -> int:
    """Cuantas jugadas activas del sorteo tienen exactamente esos numeros (incluida la propia)."""
    return (
        sesion.query(Jugada)
        .filter(
            Jugada.sorteo_id == sorteo_id,
            Jugada.numeros == numeros_clave,
            Jugada.estado.in_(ESTADOS_ACTIVAS),
        )
        .count()
    )


@router.get("/sorteos")
def sorteos_abiertos(sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado.in_([EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO]))
        .order_by(Sorteo.fecha)
        .all()
    )
    return [_sorteo_out(s) for s in sorteos]


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    vendedor = sesion.get(Usuario, jugador.padre_id) if jugador.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor no esta activo")
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    try:
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, jugador_id=jugador.id, jugador_nombre=jugador.nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": jugada.id,
        "numeros": jugada.numeros,
        "precio": jugada.precio,
        "estado": jugada.estado.value,
    }


@router.get("/jugadas")
def mis_jugadas(sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    """El jugador ve SUS propios numeros y si alguien mas juega los mismos."""
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.jugador_id == jugador.id)
        .order_by(Jugada.creada_en.desc())
        .limit(300)
        .all()
    )
    return [
        {
            "id": j.id,
            "sorteo_id": j.sorteo_id,
            "numeros": j.numeros,
            "precio": j.precio,
            "estado": j.estado.value,
            "premio": j.premio,
            "coincidencias": _coincidencias(sesion, j.sorteo_id, j.numeros),
        }
        for j in jugadas
    ]
