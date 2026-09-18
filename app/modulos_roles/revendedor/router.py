from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.modelos.juegos import EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/revendedor", tags=["revendedor"])


class JugadaCrear(BaseModel):
    sorteo_id: int
    numero: int = Field(ge=0, le=99)
    monto: float = Field(gt=0)
    jugador_nombre: str | None = None


class JugadaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sorteo_id: int
    numero: int
    monto: float
    jugador_nombre: str | None
    estado: str
    premio: float | None


class SorteoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    modulo: str
    fecha_sorteo: datetime
    estado: str
    premio_fijo: float | None
    pozo_acumulado: float | None


@router.get("/sorteos", response_model=list[SorteoOut])
def ver_sorteos_abiertos(
    sesion: Session = Depends(obtener_sesion),
    revendedor: Usuario = Depends(requerir_rol(RolUsuario.REVENDEDOR)),
):
    """Sorteos disponibles para cargar jugadas."""
    return (
        sesion.query(Sorteo)
        .filter(Sorteo.estado == EstadoSorteo.PROGRAMADO)
        .order_by(Sorteo.fecha_sorteo)
        .all()
    )


@router.post("/jugadas", response_model=JugadaOut)
def cargar_jugada(
    datos: JugadaCrear,
    sesion: Session = Depends(obtener_sesion),
    revendedor: Usuario = Depends(requerir_rol(RolUsuario.REVENDEDOR)),
):
    """El revendedor carga una jugada. Queda pendiente de aprobacion."""
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None or sorteo.estado != EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="El sorteo no esta disponible para cargar jugadas")
    jugada = Jugada(
        sorteo_id=sorteo.id,
        revendedor_id=revendedor.id,
        numero=datos.numero,
        monto=datos.monto,
        jugador_nombre=datos.jugador_nombre,
    )
    sesion.add(jugada)
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(
        sesion,
        "JUGADA_CARGADA",
        detalle=f"sorteo={sorteo.id} numero={jugada.numero} monto={jugada.monto}",
        usuario=revendedor,
    )
    sesion.commit()
    return jugada


@router.get("/jugadas", response_model=list[JugadaOut])
def mis_jugadas(
    sesion: Session = Depends(obtener_sesion),
    revendedor: Usuario = Depends(requerir_rol(RolUsuario.REVENDEDOR)),
):
    """Historial de jugadas del revendedor."""
    return (
        sesion.query(Jugada)
        .filter(Jugada.revendedor_id == revendedor.id)
        .order_by(Jugada.creada_en.desc())
        .limit(200)
        .all()
    )
