import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_rol
from app.core.security import hash_password
from app.modulos_juegos import motor
from app.modulos_juegos.buscador import _zona
from app.modulos_juegos.jugadas_core import crear_cupo, crear_jugada
from app.modulos_juegos.modalidades import obtener
from app.modulos_juegos.motor import aprobar_jugada, obtener_reglas
from app.modelos.juegos import (
    CupoRevendedor,
    EstadoJugada,
    EstadoSorteo,
    Jugada,
    LiquidacionRevendedor,
    LiquidacionVendedor,
    PagoRevendedor,
    Sorteo,
)
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/vendedor", tags=["vendedor"])

vendedor_dep = Depends(requerir_rol(RolUsuario.VENDEDOR))

ESTADOS_VENDIDOS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]
NUMEROS_OCULTOS = "••• (numeros ocultos)"


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
    codigo: str | None = Field(default=None, max_length=10)
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    password: str | None = None
    activo: bool | None = None


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


class MarcarPago(BaseModel):
    pagado: bool = True


class CuposVender(BaseModel):
    sorteo_id: int
    jugador_id: int
    cantidad: int = Field(ge=1, le=50)


class CupoRevAsignar(BaseModel):
    sorteo_id: int
    cantidad: int = Field(ge=1)


class PagoRevCrear(BaseModel):
    sorteo_id: int
    cantidad_jugadas: int = Field(ge=1)


class LiquidacionRevCrear(BaseModel):
    desde: date
    hasta: date


def _comision_propia(vendedor: Usuario, reglas) -> float:
    return vendedor.comision_pct if vendedor.comision_pct is not None else reglas.vendedor_pct


def _mio(sesion: Session, jugada_id: int, vendedor: Usuario) -> Jugada:
    jugada = sesion.get(Jugada, jugada_id)
    if jugada is None or jugada.vendedor_id != vendedor.id:
        raise HTTPException(status_code=404, detail="Jugada no encontrada en tu linea")
    return jugada


def _mio_rev(sesion: Session, revendedor_id: int, vendedor: Usuario) -> Usuario:
    rev = sesion.get(Usuario, revendedor_id)
    if rev is None or rev.padre_id != vendedor.id or rev.rol != RolUsuario.REVENDEDOR:
        raise HTTPException(status_code=404, detail="Revendedor no encontrado en tu linea")
    return rev


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


def _cobro_out(liq: LiquidacionVendedor):
    return {
        "id": liq.id,
        "desde": liq.desde.isoformat(),
        "hasta": liq.hasta.isoformat(),
        "monto": liq.monto,
        "detalle": _normalizar_detalle(liq.detalle),
        "pagado_admin": bool(liq.pagado_admin),
        "cobrado_vendedor": bool(liq.cobrado_vendedor),
        "pagado_en": liq.pagado_en.isoformat() if liq.pagado_en else None,
        "cobrado_en": liq.cobrado_en.isoformat() if liq.cobrado_en else None,
    }

def _normalizar_detalle(crudo):
    try:
        d = json.loads(crudo) if crudo else []
    except Exception:
        d = []
    if isinstance(d, dict):
        return {"por_sorteo": d.get("por_sorteo", []), "jugada_ids": d.get("jugada_ids", [])}
    if isinstance(d, list):
        return {"por_sorteo": d, "jugada_ids": []}
    return {"por_sorteo": [], "jugada_ids": []}

def _liq_rev_out(liq: LiquidacionRevendedor, sesion: Session):
    rev = sesion.get(Usuario, liq.revendedor_id)
    return {
        "id": liq.id,
        "revendedor_id": liq.revendedor_id,
        "revendedor": (rev.nombre if rev else "-"),
        "revendedor_usuario": (rev.usuario if rev else "-"),
        "desde": liq.desde.isoformat(),
        "hasta": liq.hasta.isoformat(),
        "monto": liq.monto,
        "detalle": _normalizar_detalle(liq.detalle),
        "pagado_vendedor": bool(liq.pagado_vendedor),
        "cobrado_revendedor": bool(liq.cobrado_revendedor),
        "pagado_en": liq.pagado_en.isoformat() if liq.pagado_en else None,
        "cobrado_en": liq.cobrado_en.isoformat() if liq.cobrado_en else None,
        "creada_en": liq.creada_en.isoformat() if liq.creada_en else None,
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
        {
            "id": r.id,
            "usuario": r.usuario,
            "nombre": r.nombre,
            "codigo": r.codigo,
            "comision_pct": r.comision_pct,
            "telefono": r.telefono,
            "activo": r.activo,
        }
        for r in revs
    ]


@router.put("/revendedores/{revendedor_id}")
def editar_revendedor(revendedor_id: int, datos: RevendedorEditar, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    reglas = obtener_reglas(sesion)
    if datos.codigo is not None:
        codigo = datos.codigo.upper()
        otro = sesion.query(Usuario).filter(Usuario.codigo == codigo, Usuario.id != revendedor_id).first()
        if otro:
            raise HTTPException(status_code=400, detail="El codigo ya existe")
        rev.codigo = codigo
    if datos.password:
        rev.password_hash = hash_password(datos.password)
    if datos.comision_pct is not None:
        if datos.comision_pct > _comision_propia(vendedor, reglas):
            raise HTTPException(status_code=400, detail="La comision no puede superar la tuya")
        rev.comision_pct = datos.comision_pct
    for campo in ("nombre", "telefono", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(rev, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "REVENDEDOR_EDITADO", detalle=rev.usuario, usuario=vendedor)
    sesion.commit()
    return {"id": rev.id, "usuario": rev.usuario, "codigo": rev.codigo, "comision_pct": rev.comision_pct, "activo": rev.activo}


@router.delete("/revendedores/{revendedor_id}")
def eliminar_revendedor(revendedor_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    jugadores = sesion.query(Usuario).filter(Usuario.revendedor_padre_id == rev.id).count()
    if jugadores > 0:
        raise HTTPException(status_code=400, detail=f"El revendedor tiene {jugadores} jugadores: no se puede eliminar. Desactivalo.")
    jugadas = sesion.query(Jugada).filter(Jugada.revendedor_id == rev.id).count()
    if jugadas > 0:
        raise HTTPException(status_code=400, detail=f"El revendedor tiene {jugadas} jugadas: no se puede eliminar. Desactivalo.")
    nombre = rev.usuario
    sesion.delete(rev)
    sesion.commit()
    auditoria.registrar(sesion, "REVENDEDOR_ELIMINADO", detalle=f"{nombre} por {vendedor.usuario}", usuario=vendedor)
    sesion.commit()
    return {"ok": True}


# ---------- JUGADORES PROPIOS ----------

@router.post("/jugadores")
def crear_jugador(datos: JugadorCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    jugador = Usuario(
        usuario=datos.usuario,
        password_hash=hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.JUGADOR,
        padre_id=vendedor.id,
        activo=True,
        datos_cobro=datos.datos_cobro,
        cobro_transferencia=datos.cobro_transferencia,
    )
    sesion.add(jugador)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_CREADO_MANUAL", detalle=f"{jugador.usuario} por {vendedor.usuario} cobro={jugador.datos_cobro}", usuario=vendedor)
    sesion.commit()
    return {"id": jugador.id, "usuario": jugador.usuario, "nombre": jugador.nombre}


@router.get("/jugadores")
def listar_jugadores(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadores = sesion.query(Usuario).filter(Usuario.padre_id == vendedor.id, Usuario.rol == RolUsuario.JUGADOR).all()
    salida = []
    for j in jugadores:
        rev = sesion.get(Usuario, j.revendedor_padre_id) if j.revendedor_padre_id else None
        salida.append(
            {
                "id": j.id,
                "usuario": j.usuario,
                "nombre": j.nombre,
                "telefono": j.telefono,
                "activo": j.activo,
                "datos_cobro": j.datos_cobro,
                "cobro_transferencia": bool(j.cobro_transferencia),
                "revendedor": rev.usuario if rev else None,
            }
        )
    return salida


@router.put("/jugadores/{jugador_id}")
def editar_jugador(jugador_id: int, datos: JugadorEditar, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugador = sesion.get(Usuario, jugador_id)
    if jugador is None or jugador.padre_id != vendedor.id or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=404, detail="Jugador no encontrado en tu linea")
    if datos.password:
        jugador.password_hash = hash_password(datos.password)
    for campo in ("nombre", "telefono", "datos_cobro", "cobro_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(jugador, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_EDITADO", detalle=jugador.usuario, usuario=vendedor)
    sesion.commit()
    return {"id": jugador.id, "usuario": jugador.usuario, "activo": jugador.activo}


@router.delete("/jugadores/{jugador_id}")
def eliminar_jugador(jugador_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugador = sesion.get(Usuario, jugador_id)
    if jugador is None or jugador.padre_id != vendedor.id or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=404, detail="Jugador no encontrado en tu linea")
    jugadas = sesion.query(Jugada).filter(Jugada.jugador_id == jugador_id).count()
    if jugadas > 0:
        raise HTTPException(status_code=400, detail=f"El jugador tiene {jugadas} jugadas: no se puede eliminar. Editalo y desactivalo.")
    nombre = jugador.usuario
    sesion.delete(jugador)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_ELIMINADO", detalle=nombre, usuario=vendedor)
    sesion.commit()
    return {"ok": True}



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


@router.get("/sorteos/{sorteo_id}/ocupados")
def numeros_ocupados(sorteo_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    return {"ocupados": motor.numeros_ocupados_rifa(sesion, sorteo)}


@router.post("/jugadas")
def cargar_jugada(datos: JugadaCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """Venta directa: valida todo primero, luego consume cupo y crea la jugada."""
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    
    # 1. Validar disponibilidad de cupo (sin consumir)
    tiene_reg, disp = motor.cupo_vendedor_disponible(sesion, sorteo, vendedor)
    if tiene_reg and (disp is None or disp < 1):
        raise HTTPException(status_code=400, detail="Sin jugadas disponibles para vender en este sorteo. Pedi mas al administrador.")
    
    # 2. Resolver jugador
    jugador_id = None
    nombre = datos.jugador_nombre
    revendedor_id = None
    if datos.jugador_id is not None:
        pj = sesion.get(Usuario, datos.jugador_id)
        if pj is None or pj.padre_id != vendedor.id or pj.rol != RolUsuario.JUGADOR:
            raise HTTPException(status_code=400, detail="Jugador invalido para tu linea")
        jugador_id = pj.id
        nombre = pj.nombre
        revendedor_id = pj.revendedor_padre_id
    
    # 3. Validar números (sin consumir cupo)
    try:
        motor.validar_numeros_rifa(sesion, sorteo, datos.numeros)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 4. Consumir cupo y crear jugada (todo en un solo try con rollback)
    try:
        if not motor.consumir_cupo_vendedor(sesion, sorteo, vendedor):
            raise ValueError("Sin jugadas disponibles para vender en este sorteo")
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, revendedor_id=revendedor_id, jugador_id=jugador_id, jugador_nombre=nombre)
        reglas = obtener_reglas(sesion)
        aprobar_jugada(sesion, jugada, reglas)
        sesion.commit()
    except ValueError as e:
        sesion.rollback()  # ← FIX: si falla, revertimos el consumo de cupo
        raise HTTPException(status_code=400, detail=str(e))
    
    aviso_iguales = motor.info_premio_compartido(sesion, sorteo, jugada.numeros, incluir_pendiente=False)
    return {"id": jugada.id, "numeros": jugada.numeros, "precio": jugada.precio, "estado": jugada.estado.value, "aviso_iguales": aviso_iguales}

# ---------- VENTA DE JUGADAS (autorizaciones) ----------

@router.post("/cupos")
def vender_cupos(datos: CuposVender, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """Vende N jugadas a un jugador. Descuenta N jugadas disponibles del vendedor."""
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    tiene_reg, disp = motor.cupo_vendedor_disponible(sesion, sorteo, vendedor)
    if tiene_reg and (disp is None or disp < datos.cantidad):
        raise HTTPException(status_code=400, detail=f"Sin jugadas suficientes: te quedan {disp} para este sorteo. Pedi mas al administrador.")
    jugador = sesion.get(Usuario, datos.jugador_id)
    if jugador is None or jugador.padre_id != vendedor.id or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=400, detail="Jugador invalido para tu linea")
    reglas = obtener_reglas(sesion)
    creadas = []
    try:
        for _ in range(datos.cantidad):
            if not motor.consumir_cupo_vendedor(sesion, sorteo, vendedor):
                raise ValueError("Sin jugadas disponibles para vender en este sorteo")
            cupo = crear_cupo(
                sesion,
                sorteo,
                vendedor,
                revendedor_id=jugador.revendedor_padre_id,
                jugador_id=jugador.id,
                jugador_nombre=jugador.nombre,
            )
            aprobar_jugada(sesion, cupo, reglas)
            creadas.append(cupo.id)
        sesion.commit()
        auditoria.registrar(
            sesion,
            "JUGADAS_VENDIDAS",
            detalle=f"sorteo={sorteo.id} jugador={jugador.usuario} cantidad={datos.cantidad}",
            usuario=vendedor,
        )
        sesion.commit()
    except ValueError as e:
        sesion.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    monto_total = round((sorteo.precio_jugada or 0.0) * len(creadas), 2)
    return {"ids": creadas, "cantidad": len(creadas), "monto_total": monto_total}


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
            "numeros": NUMEROS_OCULTOS,
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


@router.post("/jugadas/{jugada_id}/marcar-premio")
def marcar_premio(jugada_id: int, datos: MarcarPago, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugada = _mio(sesion, jugada_id, vendedor)
    if jugada.estado != EstadoJugada.GANADORA:
        raise HTTPException(status_code=400, detail="Solo se puede marcar el premio de jugadas ganadoras")
    jugada.premio_pagado = datos.pagado
    sesion.commit()
    auditoria.registrar(sesion, "PREMIO_MARCADO_VENDEDOR", detalle=f"jugada={jugada.id} pagado={datos.pagado}", usuario=vendedor)
    sesion.commit()
    return {"ok": True, "premio_pagado": bool(jugada.premio_pagado)}


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
        {"id": j.id, "sorteo_id": j.sorteo_id, "numeros": NUMEROS_OCULTOS, "precio": j.precio, "estado": j.estado.value, "premio": j.premio, "mi_comision": j.monto_vendedor}
        for j in jugadas
    ]


@router.get("/resumen")
def resumen(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    jugadas = sesion.query(Jugada).filter(Jugada.vendedor_id == vendedor.id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "mi_comision": round(sum(j.monto_vendedor or 0 for j in jugadas), 2),
        "comision_revendedores": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
    }


# ---------- CUPOS Y PAGOS DE REVENDEDORES ----------

@router.post("/revendedores/{revendedor_id}/cupos")
def asignar_cupo_rev(revendedor_id: int, datos: CupoRevAsignar, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """El vendedor cede N jugadas de SU propio cupo a un revendedor para un sorteo."""
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    tiene_reg, disp = motor.cupo_vendedor_disponible(sesion, sorteo, vendedor)
    if tiene_reg and (disp is None or disp < datos.cantidad):
        raise HTTPException(status_code=400, detail=f"Sin jugadas suficientes para ceder: te quedan {disp} en este sorteo.")
    try:
        for _ in range(datos.cantidad):
            if not motor.consumir_cupo_vendedor(sesion, sorteo, vendedor):
                raise ValueError("Sin jugadas disponibles para ceder")
        reg = (
            sesion.query(CupoRevendedor)
            .filter(CupoRevendedor.sorteo_id == sorteo.id, CupoRevendedor.revendedor_id == rev.id)
            .first()
        )
        if reg is None:
            reg = CupoRevendedor(sorteo_id=sorteo.id, vendedor_id=vendedor.id, revendedor_id=rev.id, cupo_total=datos.cantidad, cupo_usado=0)
            sesion.add(reg)
        else:
            reg.cupo_total = (reg.cupo_total or 0) + datos.cantidad
        sesion.commit()
        auditoria.registrar(sesion, "JUGADAS_REV_ASIGNADAS", detalle=f"sorteo={sorteo.id} rev={rev.usuario} +{datos.cantidad} total={reg.cupo_total}", usuario=vendedor)
        sesion.commit()
    except ValueError as e:
        sesion.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"revendedor_id": rev.id, "cupo_total": reg.cupo_total, "cupo_usado": reg.cupo_usado or 0, "disponibles": max((reg.cupo_total or 0) - (reg.cupo_usado or 0), 0)}


@router.get("/revendedores/{revendedor_id}/cupos")
def listar_cupos_rev(revendedor_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    regs = sesion.query(CupoRevendedor).filter(CupoRevendedor.revendedor_id == rev.id, CupoRevendedor.vendedor_id == vendedor.id).all()
    salida = []
    for r in regs:
        s = sesion.get(Sorteo, r.sorteo_id)
        salida.append({
            "sorteo_id": r.sorteo_id,
            "sorteo_titulo": (s.titulo or s.modalidad) if s else "-",
            "cupo_total": r.cupo_total or 0,
            "cupo_usado": r.cupo_usado or 0,
            "disponibles": max((r.cupo_total or 0) - (r.cupo_usado or 0), 0),
        })
    return salida


@router.post("/revendedores/{revendedor_id}/pagos")
def registrar_pago_rev(revendedor_id: int, datos: PagoRevCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """El vendedor confirma que el revendedor le pago X jugadas de un sorteo."""
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    monto = round((sorteo.precio_jugada or 0.0) * datos.cantidad_jugadas, 2)
    pago = PagoRevendedor(sorteo_id=sorteo.id, vendedor_id=vendedor.id, revendedor_id=rev.id, cantidad_jugadas=datos.cantidad_jugadas, monto=monto)
    sesion.add(pago)
    sesion.commit()
    auditoria.registrar(sesion, "PAGO_REV_CONFIRMADO", detalle=f"sorteo={sorteo.id} rev={rev.usuario} jugadas={datos.cantidad_jugadas} monto={monto}", usuario=vendedor)
    sesion.commit()
    return {"id": pago.id, "cantidad_jugadas": pago.cantidad_jugadas, "monto": pago.monto}


@router.get("/revendedores/{revendedor_id}/pagos")
def listar_pagos_rev(revendedor_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    pagos = sesion.query(PagoRevendedor).filter(PagoRevendedor.revendedor_id == rev.id, PagoRevendedor.vendedor_id == vendedor.id).order_by(PagoRevendedor.id.desc()).all()
    salida = []
    for p in pagos:
        s = sesion.get(Sorteo, p.sorteo_id)
        salida.append({
            "sorteo_id": p.sorteo_id,
            "sorteo_titulo": (s.titulo or s.modalidad) if s else "-",
            "cantidad_jugadas": p.cantidad_jugadas,
            "monto": p.monto,
            "creado_en": p.creado_en.isoformat() if p.creado_en else None,
        })
    return salida


@router.get("/revendedores/{revendedor_id}/cuenta")
def cuenta_rev(revendedor_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """Resumen de cuenta del revendedor: jugadas entregadas/pagadas/debe, vendido y su comision."""
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    regs = sesion.query(CupoRevendedor).filter(CupoRevendedor.revendedor_id == rev.id, CupoRevendedor.vendedor_id == vendedor.id).all()
    cedido = sum(r.cupo_total or 0 for r in regs)
    usado = sum(r.cupo_usado or 0 for r in regs)
    pagadas = sum(p.cantidad_jugadas or 0 for p in sesion.query(PagoRevendedor).filter(PagoRevendedor.revendedor_id == rev.id, PagoRevendedor.vendedor_id == vendedor.id).all())
    vendidas = sesion.query(Jugada).filter(Jugada.revendedor_id == rev.id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    compat = max(len(vendidas) - usado, 0)
    vendido = round(sum(j.precio or 0 for j in vendidas), 2)
    comision_rev = round(sum(j.monto_revendedor or 0 for j in vendidas), 2)
    return {
        "jugadas_entregadas": cedido + compat,
        "jugadas_pagadas": pagadas,
        "jugadas_debe": max(cedido + compat - pagadas, 0),
        "vendido": vendido,
        "comision_revendedor": comision_rev,
    }

# ---------- LIQUIDACIONES A REVENDEDORES (gestion del vendedor) ----------

@router.post("/revendedores/{revendedor_id}/liquidaciones")
def generar_liquidacion_rev(revendedor_id: int, datos: LiquidacionRevCrear, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    rev = _mio_rev(sesion, revendedor_id, vendedor)
    if datos.desde > datos.hasta:
        raise HTTPException(status_code=400, detail="La fecha 'desde' no puede ser posterior a 'hasta'")
    pagadas_ids = set()
    liqs_pagadas = (
        sesion.query(LiquidacionRevendedor)
        .filter(LiquidacionRevendedor.revendedor_id == revendedor_id, LiquidacionRevendedor.pagado_vendedor == True)
        .all()
    )
    for l in liqs_pagadas:
        pagadas_ids.update(_normalizar_detalle(l.detalle)["jugada_ids"])
    z = _zona()
    dt_desde = datetime.combine(datos.desde, datetime.min.time(), tzinfo=z)
    dt_hasta = datetime.combine(datos.hasta + timedelta(days=1), datetime.min.time(), tzinfo=z)
    jugadas = (
        sesion.query(Jugada)
        .join(Sorteo, Jugada.sorteo_id == Sorteo.id)
        .filter(
            Jugada.revendedor_id == revendedor_id,
            Jugada.estado.in_(ESTADOS_VENDIDOS),
            Sorteo.fecha >= dt_desde,
            Sorteo.fecha < dt_hasta,
        )
        .all()
    )
    agrupado = {}
    ids_incluidos = []
    for j in jugadas:
        if j.id in pagadas_ids:
            continue
        ids_incluidos.append(j.id)
        d = agrupado.setdefault(j.sorteo_id, {"jugadas": 0, "vendido": 0.0, "comision": 0.0})
        d["jugadas"] += 1
        d["vendido"] = round(d["vendido"] + (j.precio or 0.0), 2)
        d["comision"] = round(d["comision"] + (j.monto_revendedor or 0.0), 2)
    sorteos_map = {}
    if agrupado:
        sorteos_map = {s.id: s for s in sesion.query(Sorteo).filter(Sorteo.id.in_(list(agrupado.keys()))).all()}
    detalle = []
    total = 0.0
    for sid, d in agrupado.items():
        s = sorteos_map.get(sid)
        total = round(total + d["comision"], 2)
        detalle.append({
            "sorteo_id": sid,
            "modalidad": (s.modalidad if s else "-"),
            "horario": (s.horario if s else "-"),
            "fecha": (s.fecha.date().isoformat() if s else "-"),
            "jugadas": d["jugadas"],
            "vendido": d["vendido"],
            "comision": d["comision"],
        })
    detalle.sort(key=lambda x: (x["fecha"], x["sorteo_id"]))
    liq = LiquidacionRevendedor(
        revendedor_id=revendedor_id,
        vendedor_id=vendedor.id,
        desde=datos.desde,
        hasta=datos.hasta,
        monto=total,
        detalle=json.dumps({"por_sorteo": detalle, "jugada_ids": ids_incluidos}),
    )
    sesion.add(liq)
    sesion.commit()
    sesion.refresh(liq)
    auditoria.registrar(sesion, "LIQUIDACION_REV_GENERADA", detalle=f"rev={revendedor_id} {datos.desde}..{datos.hasta} monto={total}", usuario=vendedor)
    sesion.commit()
    return _liq_rev_out(liq, sesion)


@router.get("/liquidaciones-rev")
def listar_liquidaciones_rev(revendedor_id: int | None = None, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    consulta = sesion.query(LiquidacionRevendedor).filter(LiquidacionRevendedor.vendedor_id == vendedor.id)
    if revendedor_id is not None:
        consulta = consulta.filter(LiquidacionRevendedor.revendedor_id == revendedor_id)
    liqs = consulta.order_by(LiquidacionRevendedor.id.desc()).all()
    return [_liq_rev_out(l, sesion) for l in liqs]


@router.post("/liquidaciones-rev/{liq_id}/marcar-pagado")
def marcar_liquidacion_rev_pagada(liq_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    liq = sesion.get(LiquidacionRevendedor, liq_id)
    if liq is None or liq.vendedor_id != vendedor.id:
        raise HTTPException(status_code=404, detail="Liquidacion no encontrada")
    liq.pagado_vendedor = True
    liq.pagado_en = datetime.now(_zona())
    sesion.commit()
    auditoria.registrar(sesion, "LIQUIDACION_REV_PAGADA", detalle=f"liq={liq_id}", usuario=vendedor)
    sesion.commit()
    return _liq_rev_out(liq, sesion)


# ---------- RESULTADOS (ultimos 5 liquidados) ----------

@router.get("/resultados")
def resultados(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
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
        mis_ganadoras = [g for g in ganadoras if g.vendedor_id == vendedor.id]
        tuve = (
            sesion.query(Jugada)
            .filter(Jugada.sorteo_id == s.id, Jugada.vendedor_id == vendedor.id)
            .count()
        ) > 0
        salida.append({
            "sorteo_id": s.id,
            "titulo": s.titulo,
            "modalidad": s.modalidad,
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "premio_nombre": s.premio_nombre,
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


# ---------- MIS COBROS (liquidaciones de comisiones del admin) ----------

@router.get("/cobros")
def mis_cobros(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    liqs = (
        sesion.query(LiquidacionVendedor)
        .filter(LiquidacionVendedor.vendedor_id == vendedor.id)
        .order_by(LiquidacionVendedor.id.desc())
        .all()
    )
    return [_cobro_out(l) for l in liqs]


@router.post("/cobros/{liq_id}/confirmar-cobro")
def confirmar_cobro(liq_id: int, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    liq = sesion.get(LiquidacionVendedor, liq_id)
    if liq is None or liq.vendedor_id != vendedor.id:
        raise HTTPException(status_code=404, detail="Liquidacion no encontrada")
    if not liq.pagado_admin:
        raise HTTPException(status_code=400, detail="El administrador todavia no marco el pago; espera a que te lo confirme")
    liq.cobrado_vendedor = True
    liq.cobrado_en = datetime.now(_zona())
    sesion.commit()
    auditoria.registrar(sesion, "COBRO_VENDEDOR_CONFIRMADO", detalle=f"liq={liq_id} monto={liq.monto}", usuario=vendedor)
    sesion.commit()
    return _cobro_out(liq)

# ---------- MIS JUGADAS DISPONIBLES POR SORTEO ----------

@router.get("/mis-cupos")
def mis_cupos_vendedor(sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """Jugadas que el admin le asigno al vendedor por sorteo, con usadas y disponibles."""
    from app.modelos.juegos import CupoVendedor
    regs = sesion.query(CupoVendedor).filter(CupoVendedor.vendedor_id == vendedor.id).all()
    salida = []
    for r in regs:
        s = sesion.get(Sorteo, r.sorteo_id)
        salida.append({
            "sorteo_id": r.sorteo_id,
            "sorteo_titulo": (s.titulo or s.modalidad) if s else "-",
            "cupo_total": r.cupo_total or 0,
            "cupo_usado": r.cupo_usado or 0,
            "disponibles": max((r.cupo_total or 0) - (r.cupo_usado or 0), 0),
        })
    return salida
