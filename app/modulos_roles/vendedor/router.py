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
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, LiquidacionVendedor, Sorteo
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
    import json
    try:
        detalle = json.loads(liq.detalle) if liq.detalle else []
    except Exception:
        detalle = []
    return {
        "id": liq.id,
        "desde": liq.desde.isoformat(),
        "hasta": liq.hasta.isoformat(),
        "monto": liq.monto,
        "detalle": detalle,
        "pagado_admin": bool(liq.pagado_admin),
        "cobrado_vendedor": bool(liq.cobrado_vendedor),
        "pagado_en": liq.pagado_en.isoformat() if liq.pagado_en else None,
        "cobrado_en": liq.cobrado_en.isoformat() if liq.cobrado_en else None,
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
    rev = sesion.get(Usuario, revendedor_id)
    if rev is None or rev.padre_id != vendedor.id or rev.rol != RolUsuario.REVENDEDOR:
        raise HTTPException(status_code=404, detail="Revendedor no encontrado en tu linea")
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
    rev = sesion.get(Usuario, revendedor_id)
    if rev is None or rev.padre_id != vendedor.id or rev.rol != RolUsuario.REVENDEDOR:
        raise HTTPException(status_code=404, detail="Revendedor no encontrado en tu linea")
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
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugador_id = None
    nombre = datos.jugador_nombre
    if datos.jugador_id is not None:
        pj = sesion.get(Usuario, datos.jugador_id)
        if pj is None or pj.padre_id != vendedor.id or pj.rol != RolUsuario.JUGADOR:
            raise HTTPException(status_code=400, detail="Jugador invalido para tu linea")
        jugador_id = pj.id
        nombre = pj.nombre
    try:
        motor.validar_numeros_rifa(sesion, sorteo, datos.numeros)
        jugada = crear_jugada(sesion, sorteo, datos.numeros, vendedor, jugador_id=jugador_id, jugador_nombre=nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": jugada.id, "numeros": jugada.numeros, "precio": jugada.precio, "estado": jugada.estado.value}


# ---------- VENTA DE CUPOS (autorizaciones de jugada) ----------

@router.post("/cupos")
def vender_cupos(datos: CuposVender, sesion: Session = Depends(obtener_sesion), vendedor: Usuario = vendedor_dep):
    """Vende N cupos (jugadas aprobadas sin numeros) a un jugador de su linea.

    El cobro es fuera del sistema. Al crear cada cupo se aprueba en el acto: el precio
    se reparte y suma al pozo inmediatamente. Doble confirmacion en el frontend.
    """
    sorteo = sesion.get(Sorteo, datos.sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugador = sesion.get(Usuario, datos.jugador_id)
    if jugador is None or jugador.padre_id != vendedor.id or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=400, detail="Jugador invalido para tu linea")
    reglas = obtener_reglas(sesion)
    creadas = []
    try:
        for _ in range(datos.cantidad):
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
            "CUPOS_VENDIDOS",
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


# ---------- MIS COBROS (liquidaciones de comisiones) ----------

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
    auditoria.registrar(sesion, "COBRO_VENDEDOR_CONFIRMADO", detalle=f"liq={liq_id}", usuario=vendedor)
    sesion.commit()
    return _cobro_out(liq)
