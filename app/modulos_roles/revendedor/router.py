from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.core.security import hash_password
from app.modulos_juegos import motor
from app.modulos_juegos.jugadas_core import crear_jugada
from app.modulos_juegos.modalidades import obtener
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/revendedor", tags=["revendedor"])

rev_dep = Depends(requerir_rol(RolUsuario.REVENDEDOR))

ESTADOS_VENDIDOS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]
NUMEROS_OCULTOS = "••• (numeros ocultos)"


class JugadaCrear(BaseModel):
    sorteo_id: int
    numeros: list[int]
    jugador_nombre: str | None = None
    jugador_id: int | None = None


class JugadorCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    telefono: str = Field(min_length=5)
    datos_cobro: str = Field(min_length=1)
    cobro_transferencia: bool = True


class JugadorEditar(BaseModel):
    nombre: str | None = None
    telefono: str | None = Field(default=None, min_length=5)
    datos_cobro: str | None = Field(default=None, min_length=1)
    cobro_transferencia: bool | None = None
    password: str | None = None
    activo: bool | None = None


def _mio_jugador(sesion: Session, jugador_id: int, rev: Usuario) -> Usuario:
    jugador = sesion.get(Usuario, jugador_id)
    if jugador is None or jugador.revendedor_padre_id != rev.id or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=404, detail="Jugador no encontrado en tu linea")
    return jugador


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
        "reprogramando": s.estado == EstadoSorteo.REPROGRAMANDO,
        "imagen_url": s.imagen_url,
    }


# ---------- JUGADORES DEL REVENDEDOR (crear, editar, eliminar) ----------

@router.post("/jugadores")
def crear_jugador(datos: JugadorCrear, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    """El revendedor carga a mano un jugador: queda en la linea del vendedor duenio y atado a este revendedor."""
    vendedor = sesion.get(Usuario, rev.padre_id) if rev.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor duenio no esta activo")
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    jugador = Usuario(
        usuario=datos.usuario,
        password_hash=hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.JUGADOR,
        padre_id=vendedor.id,
        revendedor_padre_id=rev.id,
        activo=True,
        datos_cobro=datos.datos_cobro,
        cobro_transferencia=datos.cobro_transferencia,
    )
    sesion.add(jugador)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_CREADO_MANUAL", detalle=f"{jugador.usuario} por revendedor {rev.usuario}", usuario=vendedor)
    sesion.commit()
    return {"id": jugador.id, "usuario": jugador.usuario, "nombre": jugador.nombre}


@router.get("/jugadores")
def listar_jugadores(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    jugadores = sesion.query(Usuario).filter(Usuario.revendedor_padre_id == rev.id, Usuario.rol == RolUsuario.JUGADOR).all()
    return [
        {
            "id": j.id,
            "usuario": j.usuario,
            "nombre": j.nombre,
            "telefono": j.telefono,
            "activo": j.activo,
            "datos_cobro": j.datos_cobro,
            "cobro_transferencia": bool(j.cobro_transferencia),
        }
        for j in jugadores
    ]


@router.put("/jugadores/{jugador_id}")
def editar_jugador(jugador_id: int, datos: JugadorEditar, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    jugador = _mio_jugador(sesion, jugador_id, rev)
    if datos.password:
        jugador.password_hash = hash_password(datos.password)
    for campo in ("nombre", "telefono", "datos_cobro", "cobro_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(jugador, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_EDITADO", detalle=f"{jugador.usuario} por revendedor {rev.usuario}", usuario=rev)
    sesion.commit()
    return {"id": jugador.id, "usuario": jugador.usuario, "activo": jugador.activo}


@router.delete("/jugadores/{jugador_id}")
def eliminar_jugador(jugador_id: int, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    jugador = _mio_jugador(sesion, jugador_id, rev)
    jugadas = sesion.query(Jugada).filter(Jugada.jugador_id == jugador_id).count()
    if jugadas > 0:
        raise HTTPException(status_code=400, detail=f"El jugador tiene {jugadas} jugadas: no se puede eliminar. Editalo y desactivalo.")
    nombre = jugador.usuario
    sesion.delete(jugador)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_ELIMINADO", detalle=f"{nombre} por revendedor {rev.usuario}", usuario=rev)
    sesion.commit()
    return {"ok": True}


# ---------- SORTEOS Y JUGADAS ----------

@router.get("/sorteos")
def sorteos_abiertos(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado.in_([EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO]))
        .order_by(Sorteo.fecha)
        .all()
    )
    return [_sorteo_out(s) for s in sorteos]


@router.get("/sorteos/{sorteo_id}/ocupados")
def numeros_ocupados(sorteo_id: int, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    """Numeros ya jugados en una rifa de numero unico (para la grilla). None si no aplica."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    return {"ocupados": motor.numeros_ocupados_rifa(sesion, sorteo)}


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    vendedor = sesion.get(Usuario, rev.padre_id) if rev.padre_id else None
    if vendedor is None or not vendedor.activo:
        raise HTTPException(status_code=403, detail="Tu vendedor duenio no esta activo")
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugador_id = None
    nombre = datos.jugador_nombre
    if datos.jugador_id is not None:
        pj = sesion.get(Usuario, datos.jugador_id)
        if pj is None or pj.revendedor_padre_id != rev.id or pj.rol != RolUsuario.JUGADOR:
            raise HTTPException(status_code=400, detail="Jugador invalido para tu linea")
        jugador_id = pj.id
        nombre = pj.nombre
    try:
        motor.validar_numeros_rifa(sesion, sorteo, datos.numeros)
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, revendedor_id=rev.id, jugador_id=jugador_id, jugador_nombre=nombre)
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
        {"id": j.id, "sorteo_id": j.sorteo_id, "numeros": NUMEROS_OCULTOS, "precio": j.precio, "estado": j.estado.value, "premio": j.premio, "mi_comision": j.monto_revendedor}
        for j in jugadas
    ]


@router.get("/resumen")
def resumen(sesion: Session = Depends(obtener_sesion), rev: Usuario = rev_dep):
    """Cuenta todas las jugadas que cargaste y fueron aprobadas (incluidas ya liquidadas)."""
    jugadas = sesion.query(Jugada).filter(Jugada.revendedor_id == rev.id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "mi_comision": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
    }


# ---------- RESULTADOS (ultimos 5 liquidados) ----------

@router.get("/resultados")
def resultados(sesion: Session = Depends(obtener_sesion), revendedor: Usuario = rev_dep):
    """Ultimos 5 sorteos liquidados con sus resultados y los jugadores ganadores de tu linea."""
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
        mis_ganadoras = [g for g in ganadoras if g.revendedor_id == revendedor.id]
        tuve = (
            sesion.query(Jugada)
            .filter(Jugada.sorteo_id == s.id, Jugada.revendedor_id == revendedor.id)
            .count()
        ) > 0
        salida.append({
            "sorteo_id": s.id,
            "titulo": s.titulo,
            "modalidad": s.modalidad,
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "resultados": s.lista_resultados,
            "cantidad_ganadores": len(ganadoras),
            "tuve_jugadores": tuve,
            "mis_ganadores": [
                {
                    "jugada_id": g.id,
                    "jugador_nombre": g.jugador_nombre,
                    "premio": g.premio,
                    "premio_pagado": g.premio_pagado,
                    "premio_cobrado": g.premio_cobrado,
                }
                for g in mis_ganadoras
            ],
        })
    return salida
