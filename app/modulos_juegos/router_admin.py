from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_permiso
from app.modulos_juegos.motor import liquidar_sorteo
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, ModuloJuego, Sorteo
from app.modelos.usuario import Usuario

router = APIRouter(prefix="/admin", tags=["juegos"])


class SorteoCrear(BaseModel):
    modulo: ModuloJuego
    fecha_sorteo: datetime
    premio_fijo: float | None = Field(default=None, gt=0)


class ResultadoCargar(BaseModel):
    numero: int = Field(ge=0, le=99)


class JugadaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sorteo_id: int
    revendedor_id: int
    jugador_nombre: str | None
    numero: int
    monto: float
    estado: str
    premio: float | None
    comision_monto: float | None


@router.post("/sorteos")
def crear_sorteo(
    datos: SorteoCrear,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    """Crea un sorteo. Si es semanal, hereda el pozo acumulado anterior."""
    pozo = 0.0
    if datos.modulo == ModuloJuego.SEMANAL:
        ultimo = (
            sesion.query(Sorteo)
            .filter(Sorteo.modulo == ModuloJuego.SEMANAL)
            .order_by(Sorteo.id.desc())
            .first()
        )
        if ultimo is not None and ultimo.estado == EstadoSorteo.LIQUIDADO:
            pozo = ultimo.pozo_acumulado or 0.0
    sorteo = Sorteo(
        modulo=datos.modulo,
        fecha_sorteo=datos.fecha_sorteo,
        premio_fijo=datos.premio_fijo,
        pozo_acumulado=pozo,
    )
    sesion.add(sorteo)
    sesion.commit()
    sesion.refresh(sorteo)
    auditoria.registrar(sesion, "SORTEO_CREADO", detalle=f"{sorteo.modulo.value} id={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"id": sorteo.id, "modulo": sorteo.modulo.value, "estado": sorteo.estado.value, "pozo_acumulado": pozo}


@router.get("/sorteos")
def listar_sorteos(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    sorteos = sesion.query(Sorteo).order_by(Sorteo.id.desc()).limit(100).all()
    return [
        {
            "id": s.id,
            "modulo": s.modulo.value,
            "fecha_sorteo": s.fecha_sorteo.isoformat(),
            "estado": s.estado.value,
            "resultado_numero": s.resultado_numero,
            "premio_fijo": s.premio_fijo,
            "pozo_acumulado": s.pozo_acumulado,
        }
        for s in sorteos
    ]


@router.post("/sorteos/{sorteo_id}/cerrar")
def cerrar_sorteo(
    sorteo_id: int,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="El sorteo no esta en estado programado")
    sorteo.estado = EstadoSorteo.CERRADO
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_CERRADO", detalle=f"sorteo={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value}


@router.post("/sorteos/{sorteo_id}/resultado")
def cargar_resultado(
    sorteo_id: int,
    datos: ResultadoCargar,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("cargar_resultados")),
):
    """Carga el numero oficial y liquida el sorteo con el motor de juegos."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="El sorteo ya esta liquidado")
    if sorteo.estado == EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="Primero cerrá el sorteo")
    sorteo.resultado_numero = datos.numero
    resumen = liquidar_sorteo(sorteo, sesion)
    auditoria.registrar(sesion, "RESULTADO_CARGADO", detalle=f"sorteo={sorteo.id} numero={datos.numero}", usuario=admin)
    auditoria.registrar(sesion, "SORTEO_LIQUIDADO", detalle=str(resumen), usuario=admin)
    sesion.commit()
    return resumen


@router.get("/jugadas/pendientes", response_model=list[JugadaOut])
def jugadas_pendientes(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    return (
        sesion.query(Jugada)
        .filter(Jugada.estado == EstadoJugada.PENDIENTE)
        .order_by(Jugada.creada_en)
        .limit(200)
        .all()
    )


@router.post("/jugadas/{jugada_id}/aprobar", response_model=JugadaOut)
def aprobar_jugada(
    jugada_id: int,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    jugada = sesion.get(Jugada, jugada_id)
    if jugada is None:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    if jugada.estado != EstadoJugada.PENDIENTE:
        raise HTTPException(status_code=400, detail="La jugada no esta pendiente")
    revendedor = sesion.get(Usuario, jugada.revendedor_id)
    jugada.estado = EstadoJugada.APROBADA
    jugada.comision_pct = revendedor.comision_pct if revendedor else None
    jugada.comision_monto = (
        round(jugada.monto * (revendedor.comision_pct or 0) / 100, 2) if revendedor else None
    )
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(sesion, "JUGADA_APROBADA", detalle=f"jugada={jugada.id}", usuario=admin)
    sesion.commit()
    return jugada


@router.post("/jugadas/{jugada_id}/rechazar", response_model=JugadaOut)
def rechazar_jugada(
    jugada_id: int,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    jugada = sesion.get(Jugada, jugada_id)
    if jugada is None:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    if jugada.estado != EstadoJugada.PENDIENTE:
        raise HTTPException(status_code=400, detail="La jugada no esta pendiente")
    jugada.estado = EstadoJugada.RECHAZADA
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(sesion, "JUGADA_RECHAZADA", detalle=f"jugada={jugada.id}", usuario=admin)
    sesion.commit()
    return jugada


@router.get("/sorteos/{sorteo_id}/resumen")
def resumen_sorteo(
    sorteo_id: int,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("configurar_sorteos")),
):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    recaudado = sum(j.monto for j in aprobadas)
    comisiones = sum(j.comision_monto or 0 for j in aprobadas)
    premios = sum(j.premio or 0 for j in aprobadas)
    ganadoras = [j.id for j in aprobadas if j.estado == EstadoJugada.GANADORA]
    return {
        "sorteo_id": sorteo.id,
        "modulo": sorteo.modulo.value,
        "estado": sorteo.estado.value,
        "resultado_numero": sorteo.resultado_numero,
        "jugadas_aprobadas": len(aprobadas),
        "recaudado": round(recaudado, 2),
        "comisiones": round(comisiones, 2),
        "premios": round(premios, 2),
        "ganadoras": ganadoras,
        "pozo_acumulado": sorteo.pozo_acumulado,
    }
