from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modulos_juegos import motor
from app.modulos_juegos.buscador import _zona
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
        "hora_cierre": s.hora_cierre,
        "pozo": s.pozo_actual,
        "pozo_inicial": s.pozo_inicial,
        "estado": s.estado.value,
        "precio_jugada": s.precio_jugada,
        "solo_participantes": s.solo_participantes,
        "participantes": [n.strip() for n in (s.participantes or "").split("|") if n.strip()] if s.solo_participantes else None,
        "titulo": s.titulo,
        "premio_nombre": s.premio_nombre,
        "reprogramando": s.estado == EstadoSorteo.REPROGRAMANDO,
        "imagen_url": s.imagen_visible,
    }


def _puedo_jugar(s: Sorteo, jugador: Usuario, reglas) -> bool:
    if s.estado != EstadoSorteo.PROGRAMADO:
        return False
    hhmm = s.hora_cierre or reglas.dict_horarios().get(s.horario)
    if not hhmm or ":" not in hhmm:
        return False
    try:
        hora, minuto = (int(x) for x in hhmm.split(":"))
    except ValueError:
        return False
    f = s.fecha
    cierre = datetime(f.year, f.month, f.day, hora, minuto, 0, tzinfo=_zona())
    if datetime.now(_zona()) >= cierre:
        return False
    if s.solo_participantes:
        nombres = [n.strip() for n in (s.participantes or "").split("|") if n.strip()]
        if jugador.nombre not in nombres:
            return False
    return True


def _coincidencias(sesion: Session, sorteo_id: int, numeros_clave: str) -> int:
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
    reglas = motor.obtener_reglas(sesion)
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado.in_([EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO]))
        .order_by(Sorteo.fecha)
        .all()
    )
    salida = []
    for s in sorteos:
        d = _sorteo_out(s)
        d["puedo_jugar"] = _puedo_jugar(s, jugador, reglas)
        mis = (
            sesion.query(Jugada)
            .filter(Jugada.sorteo_id == s.id, Jugada.jugador_id == jugador.id, Jugada.estado.in_(ESTADOS_ACTIVAS))
            .order_by(Jugada.creada_en)
            .all()
        )
        d["mis_jugadas"] = [j.numeros for j in mis]
        salida.append(d)
    return salida


@router.get("/sorteos/{sorteo_id}/ocupados")
def numeros_ocupados(sorteo_id: int, sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    """Numeros ya jugados en una rifa de numero unico (para la grilla). None si no aplica."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    return {"ocupados": motor.numeros_ocupados_rifa(sesion, sorteo)}


@router.get("/resultados")
def resultados(sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    """Ultimos 5 sorteos liquidados con sus resultados y las jugadas del jugador."""
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado == EstadoSorteo.LIQUIDADO)
        .order_by(Sorteo.id.desc())
        .limit(5)
        .all()
    )
    salida = []
    for s in sorteos:
        ganadoras = sesion.query(Jugada).filter(Jugada.sorteo_id == s.id, Jugada.estado == EstadoJugada.GANADORA).all()
        mis = sesion.query(Jugada).filter(Jugada.sorteo_id == s.id, Jugada.jugador_id == jugador.id).all()
        salida.append({
            "sorteo_id": s.id,
            "titulo": s.titulo,
            "modalidad": s.modalidad,
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "premio_nombre": s.premio_nombre,
            "resultados": s.lista_resultados,
            "cantidad_ganadores": len(ganadoras),
            "mis_jugadas": [
                {
                    "id": j.id,
                    "numeros": j.numeros,
                    "estado": j.estado.value,
                    "premio": j.premio,
                    "premio_pagado": j.premio_pagado,
                    "premio_cobrado": j.premio_cobrado,
                }
                for j in mis
            ],
        })
    return salida


@router.post("/jugadas/{jugada_id}/confirmar-cobro")
def confirmar_cobro(jugada_id: int, sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    j = sesion.get(Jugada, jugada_id)
    if j is None or j.jugador_id != jugador.id:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    if j.estado != EstadoJugada.GANADORA:
        raise HTTPException(status_code=400, detail="Solo podes confirmar el cobro de una jugada ganadora")
    j.premio_cobrado = True
    sesion.commit()
    return {"ok": True, "jugada_id": j.id}


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), jugador: Usuario = jug_dep):
    vendedor = sesion.get(Usuario, jugador.padre_id) if jugador.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor no esta activo")
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    reglas = motor.obtener_reglas(sesion)
    if not _puedo_jugar(sorteo, jugador, reglas):
        raise HTTPException(status_code=400, detail="Este sorteo no esta habilitado para jugar ahora")
    try:
        motor.validar_numeros_rifa(sesion, sorteo, datos.numeros)
        jugada = crear_jugada(
            sesion,
            sorteo,
            datos.numeros,
            vendedor,
            revendedor_id=jugador.revendedor_padre_id,
            jugador_id=jugador.id,
            jugador_nombre=jugador.nombre,
        )
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
