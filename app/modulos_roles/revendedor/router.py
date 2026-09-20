from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modulos_juegos.jugadas_core import crear_jugada
from app.modulos_juegos.modalidades import obtener
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/revendedor", tags=["revendedor"])

rev_dep = Depends(requerir_rol(RolUsuario.REVENDEDOR))


class JugadaCrear(BaseModel):
    sorteo_id: int
    numeros: list[int]
    jugador_nombre: str | None = None


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


@router.get("/sorteos")
def sorteos_abiertos(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado.in_([EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO]))
        .order_by(Sorteo.fecha)
        .all()
    )
    return [_sorteo_out(s) for s in sorteos]


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    vendedor = sesion.get(Usuario, rev.padre_id) if rev.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor duenio no esta activo")
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    try:
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, revendedor_id=rev.id, jugador_nombre=datos.jugador_nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": jugada.id, "numeros": jugada.numeros, "precio": jugada.precio, "estado": jugada.estado.value}


@router.get("/jugadas")
def mis_jugadas(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.revendedor_id == rev.id)
        .order_by(Jugada.creada_en.desc())
        .limit(300)
        .all()
    )
    return [
        {"id": j.id, "sorteo_id": j.sorteo_id, "numeros": j.numeros, "precio": j.precio, "estado": j.estado.value, "premio": j.premio, "mi_comision": j.monto_revendedor}
        for j in jugadas
    ]


@router.get("/resumen")
def resumen(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    jugadas = sesion.query(Jugada).filter(Jugada.revendedor_id == rev.id, Jugada.estado == EstadoJugada.APROBADA).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "mi_comision": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
    }
