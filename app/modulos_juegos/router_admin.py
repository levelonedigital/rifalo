import json
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_permiso, requerir_rol
from app.core.security import hash_password
from app.modulos_juegos import buscador, motor
from app.modulos_juegos.buscador import _actualizar_semanal, _zona, costo_a_cubrir, pozo_cubierto_total
from app.modulos_juegos.modalidades import listar, obtener
from app.modelos.juegos import Aviso, CupoVendedor, EstadoJugada, EstadoSorteo, Jugada, LiquidacionVendedor, PagoComisionVendedor, PagoVendedor, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/admin", tags=["juegos"])

admin_dep = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))

ESTADOS_VENDIDOS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]
NUMEROS_OCULTOS = "••• (numeros ocultos)"

HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_IMAGEN_CHARS = 600000


def validar_hora_cierre(valor):
    if valor is None:
        return None
    if not HORA_RE.match(valor):
        raise HTTPException(status_code=400, detail="Horario de cierre invalido: usa HH:MM (ej: 20:00)")
    return valor


def validar_imagen(imagen_data):
    if imagen_data and len(imagen_data) > MAX_IMAGEN_CHARS:
        raise HTTPException(status_code=400, detail="La imagen pesa demasiado. Usa una foto mas chica (el sistema la comprime, pero evita archivos de varios MB).")
    return imagen_data


def detalle_por_defecto(modalidad) -> str:
    base = modalidad.resumen_reglas if modalidad else ""
    return base + " Si no se cumplen las condiciones, el sorteo puede pasar a otro horario; se respetan las jugadas."


def _montos_vendidas(sesion, sorteo_id):
    jugadas = sesion.query(Jugada).filter(Jugada.sorteo_id == sorteo_id).all()
    vendidas = [j for j in jugadas if j.estado in ESTADOS_VENDIDOS]
    ganadoras = [j for j in jugadas if j.estado == EstadoJugada.GANADORA]
    return jugadas, vendidas, ganadoras


def _ganancia_admin(sorteo, sesion, vendidas, ganadoras):
    modalidad = obtener(sorteo.modalidad)
    es_pf = bool(modalidad and modalidad.usa_premio_fijo)
    casa_bruta = round(sum(j.monto_casa or 0 for j in vendidas), 2)
    premios = round(sum(j.premio or 0 for j in ganadoras), 2)
    if es_pf:
        acumulado = (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)
        excedente = max(0.0, acumulado - premios)
        casa = round(casa_bruta + excedente, 2)
    else:
        casa = casa_bruta
    return casa, casa_bruta, premios, es_pf

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

def _liq_out(liq: LiquidacionVendedor, sesion: Session):
    vendedor = sesion.get(Usuario, liq.vendedor_id)
    return {
        "id": liq.id,
        "vendedor_id": liq.vendedor_id,
        "vendedor": (vendedor.nombre if vendedor else "-"),
        "vendedor_usuario": (vendedor.usuario if vendedor else "-"),
        "desde": liq.desde.isoformat(),
        "hasta": liq.hasta.isoformat(),
        "monto": liq.monto,
        "detalle": _normalizar_detalle(liq.detalle),
        "pagado_admin": bool(liq.pagado_admin),
        "cobrado_vendedor": bool(liq.cobrado_vendedor),
        "pagado_en": liq.pagado_en.isoformat() if liq.pagado_en else None,
        "cobrado_en": liq.cobrado_en.isoformat() if liq.cobrado_en else None,
        "creada_en": liq.creada_en.isoformat() if liq.creada_en else None,
    }

# ---------- ESTADO DEL BUSCADOR ----------

@router.get("/buscador/estado")
def estado_buscador(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    estado = buscador.estado_busquedas()
    sorteos_pendientes = (
        sesion.query(Sorteo)
        .filter(
            Sorteo.estado == EstadoSorteo.CERRADO,
            Sorteo.resultados.is_(None),
            Sorteo.busqueda_agotada.is_(False),
            Sorteo.modalidad != "semanal",
        )
        .all()
    )
    return {
        "busquedas_en_curso": estado,
        "sorteos_cerrados_sin_resultado": [
            {
                "id": s.id,
                "modalidad": s.modalidad,
                "horario": s.horario,
                "fecha": s.fecha.isoformat(),
                "hora_cierre": s.hora_cierre,
            }
            for s in sorteos_pendientes
        ],
    }


class SorteoCrear(BaseModel):
    modalidad: str
    horario: str
    fecha: datetime
    hora_cierre: str | None = None
    premio_fijo: float | None = Field(default=None, gt=0)
    premio_nombre: str | None = None
    pozo_inicial: float | None = Field(default=None, ge=0)
    precio_jugada: float = Field(gt=0)
    pozo_base: float = Field(ge=0)
    casa_pct: float = Field(ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    minimo_cubrir: float | None = Field(default=None, ge=0)
    imagen_url: str | None = None
    imagen_data: str | None = None
    detalle: str | None = None
    titulo: str | None = None
    busqueda_inicio_min: int | None = Field(default=None, ge=0)
    busqueda_intervalo_min: int | None = Field(default=None, ge=0)
    busqueda_duracion_min: int | None = Field(default=None, ge=0)
    semanal_dia_inicio: int | None = Field(default=None, ge=0, le=6)
    semanal_dia_fin: int | None = Field(default=None, ge=0, le=6)
    cupos_por_vendedor: int | None = Field(default=None, ge=0)


class SorteoEditar(BaseModel):
    horario: str | None = None
    fecha: datetime | None = None
    hora_cierre: str | None = None
    precio_jugada: float | None = Field(default=None, gt=0)
    pozo_base: float | None = Field(default=None, ge=0)
    casa_pct: float | None = Field(default=None, ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    premio_fijo: float | None = Field(default=None, gt=0)
    premio_nombre: str | None = None
    minimo_cubrir: float | None = Field(default=None, ge=0)
    imagen_url: str | None = None
    imagen_data: str | None = None
    detalle: str | None = None
    titulo: str | None = None
    busqueda_inicio_min: int | None = Field(default=None, ge=0)
    busqueda_intervalo_min: int | None = Field(default=None, ge=0)
    busqueda_duracion_min: int | None = Field(default=None, ge=0)
    semanal_dia_inicio: int | None = Field(default=None, ge=0, le=6)
    semanal_dia_fin: int | None = Field(default=None, ge=0, le=6)


class ResultadoCargar(BaseModel):
    numeros: list[int]


class Reprogramar(BaseModel):
    fecha: datetime
    horario: str | None = None
    hora_cierre: str | None = None


class MarcarPago(BaseModel):
    pagado: bool = True


class LiquidacionCrear(BaseModel):
    desde: date
    hasta: date


class VendedorCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    codigo: str = Field(max_length=10)
    comision_pct: float = Field(ge=0, le=100)
    telefono: str | None = None
    datos_transferencia: str | None = None


class VendedorEditar(BaseModel):
    usuario: str | None = None
    nombre: str | None = None
    telefono: str | None = None
    codigo: str | None = Field(default=None, max_length=10)
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    datos_transferencia: str | None = None
    password: str | None = None
    activo: bool | None = None

class JugadorEditarAdmin(BaseModel):
    usuario: str | None = None
    password: str | None = None
    nombre: str | None = None
    telefono: str | None = None
    datos_cobro: str | None = None
    cobro_transferencia: bool | None = None
    activo: bool | None = None

class PozoVacanteCrear(BaseModel):
    fecha: datetime


class CupoAsignar(BaseModel):
    vendedor_id: int
    cantidad: int = Field(ge=1)


class PagoVendedorCrear(BaseModel):
    vendedor_id: int
    cantidad_jugadas: int = Field(ge=1)


class PagarComision(BaseModel):
    monto: float | None = Field(default=None, gt=0)


# ---------- MODALIDADES ----------

@router.get("/modalidades")
def listar_modalidades():
    return listar()


# ---------- SORTEOS ----------

@router.post("/sorteos")
def crear_sorteo(datos: SorteoCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    modalidad = obtener(datos.modalidad)
    if modalidad is None:
        raise HTTPException(status_code=400, detail=f"Modalidad {datos.modalidad} no existe")
    reglas = motor.obtener_reglas(sesion)
    if datos.horario not in reglas.dict_horarios():
        raise HTTPException(status_code=400, detail="Horario inexistente en las reglas")
    if datos.vendedor_pct is None:
        datos.vendedor_pct = reglas.vendedor_pct
    if datos.casa_pct + datos.vendedor_pct > 100:
        raise HTTPException(status_code=400, detail="Casa + vendedores no puede superar el 100%")
    validar_imagen(datos.imagen_data)
    hora_cierre = validar_hora_cierre(datos.hora_cierre)
    pozo = datos.pozo_inicial if datos.pozo_inicial is not None else datos.pozo_base
    busq_inicio = datos.busqueda_inicio_min if datos.busqueda_inicio_min is not None else reglas.busqueda_inicio_min
    busq_intervalo = datos.busqueda_intervalo_min if datos.busqueda_intervalo_min is not None else reglas.busqueda_intervalo_min
    busq_duracion = datos.busqueda_duracion_min if datos.busqueda_duracion_min is not None else reglas.busqueda_duracion_min
    sem_ini = datos.semanal_dia_inicio if datos.semanal_dia_inicio is not None else reglas.semanal_dia_inicio
    sem_fin = datos.semanal_dia_fin if datos.semanal_dia_fin is not None else reglas.semanal_dia_fin
    titulo = datos.titulo
    if not titulo:
        titulo = f"{modalidad.nombre} {datos.horario.capitalize()}"
    sorteo = Sorteo(
        modalidad=datos.modalidad,
        horario=datos.horario,
        fecha=datos.fecha,
        hora_cierre=hora_cierre,
        estado=EstadoSorteo.PREPARACION,
        premio_fijo=datos.premio_fijo,
        premio_nombre=(datos.premio_nombre or None),
        pozo_inicial=pozo,
        precio_jugada=datos.precio_jugada,
        pozo_base=datos.pozo_base,
        casa_pct=datos.casa_pct,
        vendedor_pct=datos.vendedor_pct,
        minimo_cubrir=datos.minimo_cubrir,
        imagen_url=datos.imagen_url,
        imagen_data=datos.imagen_data,
        detalle=datos.detalle or detalle_por_defecto(modalidad),
        titulo=titulo,
        busqueda_inicio_min=busq_inicio,
        busqueda_intervalo_min=busq_intervalo,
        busqueda_duracion_min=busq_duracion,
        semanal_dia_inicio=sem_ini,
        semanal_dia_fin=sem_fin,
    )
    sesion.add(sorteo)
    sesion.commit()
    sesion.refresh(sorteo)
    if datos.cupos_por_vendedor:
        vendedores = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.VENDEDOR, Usuario.activo.is_(True)).all()
        for v in vendedores:
            sesion.add(CupoVendedor(sorteo_id=sorteo.id, vendedor_id=v.id, cupo_total=int(datos.cupos_por_vendedor), cupo_usado=0))
        sesion.commit()
    auditoria.registrar(sesion, "SORTEO_CREADO", detalle=f"{sorteo.modalidad} {sorteo.horario} id={sorteo.id} pozo={pozo} jugadas_por_vendedor={datos.cupos_por_vendedor} (en preparacion)", usuario=admin)
    sesion.commit()
    return {"id": sorteo.id, "modalidad": sorteo.modalidad, "horario": sorteo.horario, "pozo_inicial": pozo, "titulo": sorteo.titulo}


@router.post("/sorteos/{sorteo_id}/activar")
def activar_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.PREPARACION:
        raise HTTPException(status_code=400, detail="Solo se puede activar un sorteo en preparacion")
    sorteo.estado = EstadoSorteo.PROGRAMADO
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_ACTIVADO", detalle=f"sorteo={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value}


@router.post("/sorteos/{sorteo_id}/desactivar")
def desactivar_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="Solo se puede desactivar un sorteo programado (activo)")
    sorteo.estado = EstadoSorteo.PREPARACION
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_DESACTIVADO", detalle=f"sorteo={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value}


@router.put("/sorteos/{sorteo_id}")
def editar_sorteo(sorteo_id: int, datos: SorteoEditar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="Un sorteo liquidado no se puede editar")
    reglas = motor.obtener_reglas(sesion)
    cambios = datos.model_dump(exclude_none=True)
    if "imagen_data" in cambios:
        validar_imagen(cambios["imagen_data"])
    if "hora_cierre" in cambios:
        cambios["hora_cierre"] = validar_hora_cierre(cambios["hora_cierre"])
    if "horario" in cambios and cambios["horario"] not in reglas.dict_horarios():
        raise HTTPException(status_code=400, detail="Horario inexistente en las reglas")
    if "casa_pct" in cambios and "vendedor_pct" in cambios and cambios["casa_pct"] + cambios["vendedor_pct"] > 100:
        raise HTTPException(status_code=400, detail="Casa + vendedores no puede superar el 100%")
    for campo, valor in cambios.items():
        setattr(sorteo, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_EDITADO", detalle=f"sorteo={sorteo.id} campos={list(cambios.keys())}", usuario=admin)
    sesion.commit()
    return {"ok": True, "id": sorteo.id}


@router.delete("/sorteos/{sorteo_id}")
def borrar_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="Un sorteo liquidado no se puede borrar")
    jugadas = sesion.query(Jugada).filter(Jugada.sorteo_id == sorteo.id).count()
    if jugadas > 0:
        raise HTTPException(status_code=400, detail=f"El sorteo tiene {jugadas} jugadas: no se puede borrar. Usa Cancelar horario o Reprogramar.")
    sesion.delete(sorteo)
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_BORRADO", detalle=f"sorteo={sorteo_id}", usuario=admin)
    sesion.commit()
    return {"ok": True}


@router.get("/sorteos")
def listar_sorteos(sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteos = sesion.query(Sorteo).order_by(Sorteo.id.desc()).limit(100).all()
    salida = []
    for s in sorteos:
        costo = costo_a_cubrir(s)
        cubierto = pozo_cubierto_total(s)
        modalidad = obtener(s.modalidad)
        es_pf = bool(modalidad and modalidad.usa_premio_fijo)
        gan = (
            sesion.query(Jugada)
            .filter(Jugada.sorteo_id == s.id, Jugada.estado == EstadoJugada.GANADORA)
            .all()
        )
        salida.append(
            {
                "id": s.id,
                "modalidad": s.modalidad,
                "horario": s.horario,
                "fecha": s.fecha.isoformat(),
                "hora_cierre": s.hora_cierre,
                "estado": s.estado.value,
                "resultados": s.resultados,
                "pozo": s.pozo_actual,
                "recaudado": s.recaudado,
                "pozo_cubierto": cubierto,
                "solo_participantes": s.solo_participantes,
                "busqueda_agotada": s.busqueda_agotada,
                "precio_jugada": s.precio_jugada,
                "pozo_base": s.pozo_base,
                "casa_pct": s.casa_pct,
                "vendedor_pct": s.vendedor_pct,
                "minimo_cubrir": s.minimo_cubrir,
                "imagen_url": s.imagen_visible,
                "premio_nombre": s.premio_nombre,
                "detalle": s.detalle,
                "titulo": s.titulo,
                "es_premio_fijo": es_pf,
                "requiere_pozo": bool(modalidad and modalidad.requiere_pozo),
                "costo": costo,
                "costo_cubierto": cubierto >= costo,
                "ganadores": [g.jugador_nombre for g in gan],
                "busqueda_inicio_min": s.busqueda_inicio_min,
                "busqueda_intervalo_min": s.busqueda_intervalo_min,
                "busqueda_duracion_min": s.busqueda_duracion_min,
                "semanal_dia_inicio": s.semanal_dia_inicio,
                "semanal_dia_fin": s.semanal_dia_fin,
            }
        )
    return salida


@router.get("/sorteos/{sorteo_id}/resumen")
def resumen_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugadas, vendidas, ganadoras = _montos_vendidas(sesion, sorteo_id)
    casa, casa_bruta, premios, es_pf = _ganancia_admin(sorteo, sesion, vendidas, ganadoras)
    costo = costo_a_cubrir(sorteo)
    cubierto = pozo_cubierto_total(sorteo)
    return {
        "sorteo_id": sorteo.id,
        "modalidad": sorteo.modalidad,
        "horario": sorteo.horario,
        "fecha": sorteo.fecha.isoformat(),
        "estado": sorteo.estado.value,
        "resultados": sorteo.resultados,
        "pozo": sorteo.pozo_actual,
        "pozo_cubierto": cubierto,
        "es_premio_fijo": es_pf,
        "recaudado": sorteo.recaudado or 0.0,
        "costo": costo,
        "costo_cubierto": cubierto >= costo,
        "jugadas_cargadas": len(jugadas),
        "jugadas_vendidas": len(vendidas),
        "vendido": round(sum(j.precio for j in vendidas), 2),
        "casa": casa,
        "casa_bruta": casa_bruta,
        "vendedores": round(sum(j.monto_vendedor or 0 for j in vendidas), 2),
        "revendedores": round(sum(j.monto_revendedor or 0 for j in vendidas), 2),
        "pozo_aportado": round(sum((j.monto_pozo or 0) + (j.monto_cubrir or 0) for j in vendidas), 2),
        "premios_pagados": premios,
        "ganadoras": [j.id for j in ganadoras],
    }


@router.get("/sorteos/{sorteo_id}/liquidacion")
def detalle_liquidacion(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugadas, vendidas, ganadoras = _montos_vendidas(sesion, sorteo_id)
    casa, casa_bruta, pozo_pagado, es_pf = _ganancia_admin(sorteo, sesion, vendidas, ganadoras)
    detalle_ganadoras = []
    for j in ganadoras:
        vendedor = sesion.get(Usuario, j.vendedor_id) if j.vendedor_id else None
        jugador = sesion.get(Usuario, j.jugador_id) if j.jugador_id else None
        detalle_ganadoras.append(
            {
                "jugada_id": j.id,
                "jugador": (jugador.nombre if jugador else None) or j.jugador_nombre or "-",
                "numeros": j.numeros,
                "premio": j.premio or 0.0,
                "premio_pagado": bool(j.premio_pagado),
                "premio_cobrado": bool(j.premio_cobrado),
                "vendedor": vendedor.usuario if vendedor else "-",
                "comision_vendedor": j.monto_vendedor or 0.0,
                "comision_pagada": bool(j.comision_pagada),
            }
        )
    return {
        "sorteo_id": sorteo.id,
        "modalidad": sorteo.modalidad,
        "horario": sorteo.horario,
        "fecha": sorteo.fecha.isoformat(),
        "estado": sorteo.estado.value,
        "resultados": sorteo.resultados,
        "premio_nombre": sorteo.premio_nombre,
        "es_premio_fijo": es_pf,
        "vendido": round(sum(j.precio for j in vendidas), 2),
        "casa": casa,
        "casa_bruta": casa_bruta,
        "vendedores": round(sum(j.monto_vendedor or 0 for j in vendidas), 2),
        "revendedores": round(sum(j.monto_revendedor or 0 for j in vendidas), 2),
        "pozo_formado": round(sum((j.monto_pozo or 0) + (j.monto_cubrir or 0) for j in vendidas), 2),
        "pozo_pagado": pozo_pagado,
        "cantidad_ganadoras": len(ganadoras),
        "ganadoras": detalle_ganadoras,
    }


@router.post("/sorteos/{sorteo_id}/cerrar")
def cerrar_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="El sorteo no esta en estado programado")
    sorteo.estado = EstadoSorteo.CERRADO
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_CERRADO", detalle=f"sorteo={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"ok": True}


@router.post("/sorteos/{sorteo_id}/cancelar-horario")
def cancelar_horario(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado not in (EstadoSorteo.PROGRAMADO, EstadoSorteo.CERRADO):
        raise HTTPException(status_code=400, detail="Solo se puede cancelar el horario de sorteos programados o cerrados")
    sorteo.estado = EstadoSorteo.REPROGRAMANDO
    aviso = Aviso(
        texto=(
            f"Sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario} {sorteo.fecha.strftime('%d/%m')}): "
            f"jugada cancelada por no cumplir los requisitos. Aguarda nuevo horario."
        ),
        destino="todos",
    )
    sesion.add(aviso)
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_HORARIO_CANCELADO", detalle=f"sorteo={sorteo.id}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value}


@router.post("/sorteos/{sorteo_id}/reprogramar")
def reprogramar(sorteo_id: int, datos: Reprogramar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.REPROGRAMANDO:
        raise HTTPException(status_code=400, detail="El sorteo no esta en estado reprogramando")
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    reglas = motor.obtener_reglas(sesion)
    horario = datos.horario if datos.horario else sorteo.horario
    if horario not in reglas.dict_horarios():
        raise HTTPException(status_code=400, detail="Horario inexistente en las reglas")
    hc = datos.hora_cierre.strip() if datos.hora_cierre else None
    hora_cierre = validar_hora_cierre(hc) if hc else None
    sorteo.fecha = datos.fecha
    sorteo.horario = horario
    sorteo.hora_cierre = hora_cierre
    sorteo.estado = EstadoSorteo.PROGRAMADO
    sorteo.aviso_costo_enviado = False
    aviso = Aviso(
        texto=(
            f"Sorteo #{sorteo.id} ({sorteo.modalidad} {horario}) reprogramado: "
            f"nuevo dia {datos.fecha.strftime('%d/%m/%Y')} horario {horario}."
        ),
        destino="todos",
    )
    sesion.add(aviso)
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_REPROGRAMADO", detalle=f"sorteo={sorteo.id} nueva_fecha={datos.fecha.isoformat()} horario={horario} cierre={hora_cierre}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value, "fecha": sorteo.fecha.isoformat(), "horario": sorteo.horario, "hora_cierre": sorteo.hora_cierre}


@router.post("/sorteos/{sorteo_id}/resultado")
def cargar_resultado(sorteo_id: int, datos: ResultadoCargar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("cargar_resultados"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="El sorteo ya esta liquidado")
    if sorteo.estado == EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="Primero cerra el sorteo")
    if sorteo.modalidad == "semanal":
        raise HTTPException(status_code=400, detail="El semanal se liquida solo con los sorteos diarios")
    if len(datos.numeros) != 20 or any(n < 0 or n > 9999 for n in datos.numeros):
        raise HTTPException(status_code=400, detail="Deben ser 20 numeros entre 0 y 9999 (4 digitos, se permiten repetidos)")
    sorteo.resultados = ",".join(f"{n:04d}" for n in datos.numeros)
    sorteo.busqueda_agotada = False
    reglas = motor.obtener_reglas(sesion)
    resumen = motor.liquidar_sorteo(sorteo, sesion, reglas)
    auditoria.registrar(sesion, "RESULTADO_CARGADO", detalle=f"sorteo={sorteo.id} nums={sorteo.resultados}", usuario=admin)
    auditoria.registrar(sesion, "SORTEO_LIQUIDADO", detalle=str(resumen), usuario=admin)
    sesion.commit()
    _actualizar_semanal(sesion, sorteo, reglas)
    return resumen


@router.post("/sorteos/{sorteo_id}/pozo-vacante")
def pozo_vacante(sorteo_id: int, datos: PozoVacanteCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    modalidad = obtener(sorteo.modalidad)
    if sorteo.estado != EstadoSorteo.LIQUIDADO or modalidad is None or not modalidad.requiere_pozo:
        raise HTTPException(status_code=400, detail="Solo sorteos liquidados con pozo")
    ganadoras = sesion.query(Jugada).filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.GANADORA).count()
    if ganadoras > 0:
        raise HTTPException(status_code=400, detail="Este sorteo ya tuvo ganadores")
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    nuevo = motor.crear_pozo_vacante(sesion, sorteo, datos.fecha, motor.obtener_reglas(sesion))
    nuevo.estado = EstadoSorteo.PREPARACION
    sesion.commit()
    sesion.refresh(nuevo)
    auditoria.registrar(sesion, "POZO_VACANTE_CREADO", detalle=f"origen={sorteo.id} nuevo={nuevo.id} (en preparacion)", usuario=admin)
    sesion.commit()
    return {"id": nuevo.id, "pozo_inicial": nuevo.pozo_inicial, "participantes": nuevo.participantes}


# ---------- CUPOS Y PAGOS VENDEDOR->ADMIN POR SORTEO ----------

@router.post("/sorteos/{sorteo_id}/jugadas")
def asignar_jugadas_vendedor(sorteo_id: int, datos: CupoAsignar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    """Asigna o suma jugadas disponibles a un vendedor para este sorteo. Sincroniza 'usadas' con ventas reales."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    vendedor = sesion.get(Usuario, datos.vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    reg = (
        sesion.query(CupoVendedor)
        .filter(CupoVendedor.sorteo_id == sorteo.id, CupoVendedor.vendedor_id == vendedor.id)
        .first()
    )
    if reg is None:
        reg = CupoVendedor(sorteo_id=sorteo.id, vendedor_id=vendedor.id, cupo_total=datos.cantidad, cupo_usado=0)
        sesion.add(reg)
    else:
        reg.cupo_total = (reg.cupo_total or 0) + datos.cantidad
    reg.cupo_usado = _vendidas_vendedor_sorteo(sesion, vendedor.id, sorteo.id)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADAS_VENDEDOR_ASIGNADAS", detalle=f"sorteo={sorteo.id} vendedor={vendedor.usuario} +{datos.cantidad} total={reg.cupo_total} usadas={reg.cupo_usado}", usuario=admin)
    sesion.commit()
    return {"vendedor_id": vendedor.id, "cupo_total": reg.cupo_total, "cupo_usado": reg.cupo_usado or 0, "disponibles": max((reg.cupo_total or 0) - (reg.cupo_usado or 0), 0)}

@router.get("/sorteos/{sorteo_id}/jugadas")
def listar_jugadas_vendedor(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    regs = sesion.query(CupoVendedor).filter(CupoVendedor.sorteo_id == sorteo.id).all()
    salida = []
    for r in regs:
        v = sesion.get(Usuario, r.vendedor_id)
        salida.append({
            "vendedor_id": r.vendedor_id,
            "vendedor": (v.usuario if v else "-"),
            "vendedor_nombre": (v.nombre if v else "-"),
            "jugadas_total": r.cupo_total or 0,
            "jugadas_usadas": r.cupo_usado or 0,
            "jugadas_disponibles": max((r.cupo_total or 0) - (r.cupo_usado or 0), 0),
        })
    return salida


@router.post("/sorteos/{sorteo_id}/pagos-vendedor")
def registrar_pago_vendedor(sorteo_id: int, datos: PagoVendedorCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    """El admin confirma que el vendedor le pago X jugadas de este sorteo."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    vendedor = sesion.get(Usuario, datos.vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    monto = round((sorteo.precio_jugada or 0.0) * datos.cantidad_jugadas, 2)
    pago = PagoVendedor(sorteo_id=sorteo.id, vendedor_id=vendedor.id, cantidad_jugadas=datos.cantidad_jugadas, monto=monto)
    sesion.add(pago)
    sesion.commit()
    auditoria.registrar(sesion, "PAGO_VENDEDOR_CONFIRMADO", detalle=f"sorteo={sorteo.id} vendedor={vendedor.usuario} jugadas={datos.cantidad_jugadas} monto={monto}", usuario=admin)
    sesion.commit()
    return {"id": pago.id, "vendedor_id": vendedor.id, "cantidad_jugadas": pago.cantidad_jugadas, "monto": pago.monto}


@router.get("/sorteos/{sorteo_id}/pagos-vendedor")
def listar_pagos_vendedor(sorteo_id: int, vendedor_id: int | None = None, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    consulta = sesion.query(PagoVendedor).filter(PagoVendedor.sorteo_id == sorteo.id)
    if vendedor_id is not None:
        consulta = consulta.filter(PagoVendedor.vendedor_id == vendedor_id)
    pagos = consulta.order_by(PagoVendedor.id.desc()).all()
    salida = []
    for p in pagos:
        v = sesion.get(Usuario, p.vendedor_id)
        salida.append({
            "id": p.id,
            "vendedor_id": p.vendedor_id,
            "vendedor": (v.usuario if v else "-"),
            "cantidad_jugadas": p.cantidad_jugadas,
            "monto": p.monto,
            "creado_en": p.creado_en.isoformat() if p.creado_en else None,
        })
    return salida


# ---------- JUGADAS ----------

@router.get("/jugadas")
def ver_jugadas(
    estado: str | None = None,
    sorteo_id: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = admin_dep,
):
    consulta = sesion.query(Jugada)
    if estado:
        consulta = consulta.filter(Jugada.estado == estado)
    if sorteo_id:
        consulta = consulta.filter(Jugada.sorteo_id == sorteo_id)
    jugadas = consulta.order_by(Jugada.creada_en.desc()).limit(300).all()
    salida = []
    for j in jugadas:
        vendedor = sesion.get(Usuario, j.vendedor_id)
        salida.append(
            {
                "id": j.id,
                "sorteo_id": j.sorteo_id,
                "vendedor": vendedor.usuario if vendedor else "-",
                "numeros": NUMEROS_OCULTOS,
                "precio": j.precio,
                "estado": j.estado.value,
                "premio": j.premio,
                "jugador_nombre": j.jugador_nombre,
            }
        )
    return salida


@router.get("/jugadas/{jugada_id}")
def ver_jugada(jugada_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    j = sesion.get(Jugada, jugada_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    vendedor = sesion.get(Usuario, j.vendedor_id) if j.vendedor_id else None
    revendedor = sesion.get(Usuario, j.revendedor_id) if j.revendedor_id else None
    jugador = sesion.get(Usuario, j.jugador_id) if j.jugador_id else None
    sorteo = sesion.get(Sorteo, j.sorteo_id)
    return {
        "id": j.id,
        "sorteo": {
            "id": sorteo.id,
            "modalidad": sorteo.modalidad,
            "horario": sorteo.horario,
            "fecha": sorteo.fecha.isoformat(),
            "estado": sorteo.estado.value,
        } if sorteo else None,
        "vendedor": vendedor.usuario if vendedor else "-",
        "revendedor": revendedor.usuario if revendedor else None,
        "jugador_usuario": jugador.usuario if jugador else None,
        "jugador_nombre": j.jugador_nombre,
        "numeros": NUMEROS_OCULTOS,
        "precio": j.precio,
        "estado": j.estado.value,
        "premio": j.premio,
        "monto_casa": j.monto_casa,
        "monto_vendedor": j.monto_vendedor,
        "monto_revendedor": j.monto_revendedor,
        "monto_pozo": j.monto_pozo,
        "monto_cubrir": j.monto_cubrir,
        "premio_pagado": bool(j.premio_pagado),
        "comision_pagada": bool(j.comision_pagada),
        "creada_en": j.creada_en.isoformat() if j.creada_en else None,
    }


@router.post("/jugadas/{jugada_id}/marcar-premio")
def marcar_premio_pagado(jugada_id: int, datos: MarcarPago, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    j = sesion.get(Jugada, jugada_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    if j.estado != EstadoJugada.GANADORA:
        raise HTTPException(status_code=400, detail="Solo se puede marcar el premio de jugadas ganadoras")
    j.premio_pagado = datos.pagado
    sesion.commit()
    auditoria.registrar(sesion, "PREMIO_MARCADO", detalle=f"jugada={j.id} pagado={datos.pagado}", usuario=admin)
    sesion.commit()
    return {"ok": True, "premio_pagado": bool(j.premio_pagado)}


@router.post("/jugadas/{jugada_id}/marcar-comision")
def marcar_comision_pagada(jugada_id: int, datos: MarcarPago, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    j = sesion.get(Jugada, jugada_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jugada no encontrada")
    j.comision_pagada = datos.pagado
    sesion.commit()
    auditoria.registrar(sesion, "COMISION_MARCADA", detalle=f"jugada={j.id} pagada={datos.pagado}", usuario=admin)
    sesion.commit()
    return {"ok": True, "comision_pagada": bool(j.comision_pagada)}


# ---------- VENDEDORES ----------

@router.post("/vendedores")
def crear_vendedor(datos: VendedorCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if sesion.query(Usuario).filter(Usuario.codigo == datos.codigo.upper()).first():
        raise HTTPException(status_code=400, detail="El codigo ya existe")
    vendedor = Usuario(
        usuario=datos.usuario,
        password_hash=hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.VENDEDOR,
        codigo=datos.codigo.upper(),
        comision_pct=datos.comision_pct,
        datos_transferencia=datos.datos_transferencia,
        activo=True,
    )
    sesion.add(vendedor)
    sesion.commit()
    auditoria.registrar(sesion, "VENDEDOR_CREADO", detalle=f"{vendedor.usuario} ({vendedor.codigo}) {vendedor.comision_pct}%", usuario=admin)
    sesion.commit()
    return {"id": vendedor.id, "usuario": vendedor.usuario, "codigo": vendedor.codigo}


@router.get("/vendedores")
def listar_vendedores(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    vendedores = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.VENDEDOR).order_by(Usuario.nombre).all()
    return [
        {"id": v.id, "usuario": v.usuario, "nombre": v.nombre, "codigo": v.codigo, "comision_pct": v.comision_pct, "activo": v.activo}
        for v in vendedores
    ]


@router.put("/vendedores/{vendedor_id}")
def editar_vendedor(vendedor_id: int, datos: VendedorEditar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    if datos.usuario is not None:
        if datos.usuario != vendedor.usuario:
            otro = sesion.query(Usuario).filter(Usuario.usuario == datos.usuario, Usuario.id != vendedor_id).first()
            if otro:
                raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
        vendedor.usuario = datos.usuario
    if datos.codigo is not None:
        codigo = datos.codigo.upper()
        if codigo != vendedor.codigo:
            otro = sesion.query(Usuario).filter(Usuario.codigo == codigo, Usuario.id != vendedor_id).first()
            if otro:
                raise HTTPException(status_code=400, detail="El codigo ya existe")
        vendedor.codigo = codigo
    if datos.password:
        from app.core.security import hash_password
        vendedor.password_hash = hash_password(datos.password)
    for campo in ("nombre", "telefono", "comision_pct", "datos_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(vendedor, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "VENDEDOR_EDITADO", detalle=vendedor.usuario, usuario=admin)
    sesion.commit()
    return {"id": vendedor.id, "usuario": vendedor.usuario, "comision_pct": vendedor.comision_pct, "activo": vendedor.activo}


# ---------- LIQUIDACIONES DE VENDEDORES (gestion del admin) ----------

@router.post("/vendedores/{vendedor_id}/liquidaciones")
def generar_liquidacion(vendedor_id: int, datos: LiquidacionCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    if datos.desde > datos.hasta:
        raise HTTPException(status_code=400, detail="La fecha 'desde' no puede ser posterior a 'hasta'")
    # Jugadas que ya entraron en liquidaciones PAGADAS: no se vuelven a sumar
    pagadas_ids = set()
    liqs_pagadas = (
        sesion.query(LiquidacionVendedor)
        .filter(LiquidacionVendedor.vendedor_id == vendedor_id, LiquidacionVendedor.pagado_admin == True)
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
            Jugada.vendedor_id == vendedor_id,
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
        d["comision"] = round(d["comision"] + (j.monto_vendedor or 0.0), 2)
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
    liq = LiquidacionVendedor(
        vendedor_id=vendedor_id,
        desde=datos.desde,
        hasta=datos.hasta,
        monto=total,
        detalle=json.dumps({"por_sorteo": detalle, "jugada_ids": ids_incluidos}),
    )
    sesion.add(liq)
    sesion.commit()
    sesion.refresh(liq)
    auditoria.registrar(sesion, "LIQUIDACION_VENDEDOR_GENERADA", detalle=f"vendedor={vendedor_id} {datos.desde}..{datos.hasta} monto={total}", usuario=admin)
    sesion.commit()
    return _liq_out(liq, sesion)


@router.get("/liquidaciones")
def listar_liquidaciones(vendedor_id: int | None = None, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    consulta = sesion.query(LiquidacionVendedor)
    if vendedor_id is not None:
        consulta = consulta.filter(LiquidacionVendedor.vendedor_id == vendedor_id)
    liqs = consulta.order_by(LiquidacionVendedor.id.desc()).all()
    return [_liq_out(l, sesion) for l in liqs]


@router.post("/liquidaciones/{liq_id}/marcar-pagado")
def marcar_liquidacion_pagada(liq_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    liq = sesion.get(LiquidacionVendedor, liq_id)
    if liq is None:
        raise HTTPException(status_code=404, detail="Liquidacion no encontrada")
    liq.pagado_admin = True
    liq.pagado_en = datetime.now(_zona())
    sesion.commit()
    auditoria.registrar(sesion, "LIQUIDACION_VENDEDOR_PAGADA", detalle=f"liq={liq_id}", usuario=admin)
    sesion.commit()
    return _liq_out(liq, sesion)


# ---------- JUGADORES TOTALES ----------

@router.get("/jugadores-total")
def jugadores_total(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    total = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.JUGADOR).count()
    activos = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.JUGADOR, Usuario.activo.is_(True)).count()
    return {"total": total, "activos": activos}


# ---------- BALANCE ----------

def _rango_periodo(periodo: str, ref: date):
    if periodo == "semana":
        inicio = ref - timedelta(days=ref.weekday())
        fin = inicio + timedelta(days=7)
    elif periodo == "mes":
        inicio = ref.replace(day=1)
        fin = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif periodo == "anio":
        inicio = ref.replace(month=1, day=1)
        fin = inicio.replace(year=inicio.year + 1)
    else:
        inicio = ref
        fin = ref + timedelta(days=1)
    return inicio, fin


@router.get("/balance")
def balance(
    periodo: str = "dia",
    fecha: str | None = None,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = admin_dep,
):
    try:
        ref = date.fromisoformat(fecha) if fecha else datetime.now(_zona()).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha invalida, usa AAAA-MM-DD")
    inicio, fin = _rango_periodo(periodo, ref)
    z = _zona()
    dt_inicio = datetime.combine(inicio, datetime.min.time(), tzinfo=z)
    dt_fin = datetime.combine(fin, datetime.min.time(), tzinfo=z)
    sorteos = (
        sesion.query(Sorteo)
        .filter(Sorteo.estado == EstadoSorteo.LIQUIDADO, Sorteo.fecha >= dt_inicio, Sorteo.fecha < dt_fin)
        .order_by(Sorteo.fecha)
        .all()
    )
    por_sorteo = []
    tot = {"vendido": 0.0, "casa": 0.0, "vendedores": 0.0, "revendedores": 0.0, "pozo_formado": 0.0, "premios": 0.0}
    for s in sorteos:
        _, vendidas, ganadoras = _montos_vendidas(sesion, s.id)
        casa, _cb, _pr, _pf = _ganancia_admin(s, sesion, vendidas, ganadoras)
        fila = {
            "sorteo_id": s.id,
            "modalidad": s.modalidad,
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "vendido": round(sum(j.precio for j in vendidas), 2),
            "casa": casa,
            "vendedores": round(sum(j.monto_vendedor or 0 for j in vendidas), 2),
            "revendedores": round(sum(j.monto_revendedor or 0 for j in vendidas), 2),
            "pozo_formado": round(sum((j.monto_pozo or 0) + (j.monto_cubrir or 0) for j in vendidas), 2),
            "premios": round(sum(j.premio or 0 for j in ganadoras), 2),
        }
        por_sorteo.append(fila)
        for k in tot:
            tot[k] += fila[k]
    return {
        "periodo": periodo,
        "desde": inicio.isoformat(),
        "hasta": (fin - timedelta(days=1)).isoformat(),
        "sorteos_liquidados": len(sorteos),
        "totales": {k: round(v, 2) for k, v in tot.items()},
        "por_sorteo": por_sorteo,
    }


# ---------- RESUMEN GENERAL ----------

@router.get("/resumen-general")
def resumen_general(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    jugadas = sesion.query(Jugada).filter(Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    por_sorteo = {}
    for j in jugadas:
        por_sorteo.setdefault(j.sorteo_id, []).append(j)
    casa_total = 0.0
    premios_total = 0.0
    vendido_total = 0.0
    vend_total = 0.0
    rev_total = 0.0
    for sid, js in por_sorteo.items():
        s = sesion.get(Sorteo, sid)
        if s is None:
            continue
        ganadoras = [j for j in js if j.estado == EstadoJugada.GANADORA]
        casa, _cb, premios, _pf = _ganancia_admin(s, sesion, js, ganadoras)
        casa_total += casa
        premios_total += premios
        vendido_total += sum(j.precio or 0 for j in js)
        vend_total += sum(j.monto_vendedor or 0 for j in js)
        rev_total += sum(j.monto_revendedor or 0 for j in js)
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(vendido_total, 2),
        "casa": round(casa_total, 2),
        "vendedores": round(vend_total, 2),
        "revendedores": round(rev_total, 2),
        "premios_pagados": round(premios_total, 2),
    }


# ---------- CUENTA Y COMISIONES POR VENDEDOR ----------

@router.get("/vendedores/{vendedor_id}/cuenta")
def cuenta_vendedor(vendedor_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    """Resumen de cuenta del vendedor: jugadas entregadas/pagadas/debe, vendido y comisiones."""
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    regs = sesion.query(CupoVendedor).filter(CupoVendedor.vendedor_id == vendedor_id).all()
    cedido = sum(r.cupo_total or 0 for r in regs)
    usado = sum(r.cupo_usado or 0 for r in regs)
    pagadas = sum(p.cantidad_jugadas or 0 for p in sesion.query(PagoVendedor).filter(PagoVendedor.vendedor_id == vendedor_id).all())
    vendidas = sesion.query(Jugada).filter(Jugada.vendedor_id == vendedor_id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    compat = max(len(vendidas) - usado, 0)
    vendido = round(sum(j.precio or 0 for j in vendidas), 2)
    comision_acum = round(sum(j.monto_vendedor or 0 for j in vendidas), 2)
    comision_pagada = round(sum(p.monto or 0 for p in sesion.query(PagoComisionVendedor).filter(PagoComisionVendedor.vendedor_id == vendedor_id).all()), 2)
    return {
        "jugadas_entregadas": cedido + compat,
        "jugadas_pagadas": pagadas,
        "jugadas_debe": max(cedido + compat - pagadas, 0),
        "vendido": vendido,
        "comision_acumulada": comision_acum,
        "comision_pagada": comision_pagada,
        "comision_pendiente": round(comision_acum - comision_pagada, 2),
    }

@router.get("/vendedores/{vendedor_id}/cuenta-sorteos")
def cuenta_sorteos_vendedor(vendedor_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    """Desglose por sorteo de la deuda de jugadas de un vendedor."""
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    cupos = {r.sorteo_id: r for r in sesion.query(CupoVendedor).filter(CupoVendedor.vendedor_id == vendedor_id).all()}
    vendidas_por = {}
    for j in sesion.query(Jugada).filter(Jugada.vendedor_id == vendedor_id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all():
        vendidas_por[j.sorteo_id] = vendidas_por.get(j.sorteo_id, 0) + 1
    pagadas_por = {}
    for p in sesion.query(PagoVendedor).filter(PagoVendedor.vendedor_id == vendedor_id).all():
        pagadas_por[p.sorteo_id] = pagadas_por.get(p.sorteo_id, 0) + (p.cantidad_jugadas or 0)
    sorteos_ids = set(cupos) | set(vendidas_por) | set(pagadas_por)
    salida = []
    for sid in sorteos_ids:
        s = sesion.get(Sorteo, sid)
        if s is None:
            continue
        reg = cupos.get(sid)
        entregadas = (reg.cupo_total or 0) if reg else 0
        vendidas = vendidas_por.get(sid, 0)
        pagadas = pagadas_por.get(sid, 0)
        debe_jugadas = max(vendidas - pagadas, 0)
        precio = s.precio_jugada or 0.0
        salida.append({
            "sorteo_id": sid,
            "titulo": (s.titulo or s.modalidad),
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "estado_sorteo": s.estado.value,
            "precio_jugada": precio,
            "entregadas": entregadas,
            "vendidas": vendidas,
            "disponibles": max(entregadas - vendidas, 0),
            "pagadas": pagadas,
            "debe_jugadas": debe_jugadas,
            "debe_monto": round(debe_jugadas * precio, 2),
            "sin_cupo": reg is None,
        })
    salida.sort(key=lambda x: (x["fecha"], x["sorteo_id"]))
    return salida

@router.post("/vendedores/{vendedor_id}/pagar-comision")
def pagar_comision(vendedor_id: int, datos: PagarComision, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    """El admin paga comision al vendedor. Si no pone monto, paga todo lo pendiente."""
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    vendidas = sesion.query(Jugada).filter(Jugada.vendedor_id == vendedor_id, Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    comision_acum = round(sum(j.monto_vendedor or 0 for j in vendidas), 2)
    comision_pagada = round(sum(p.monto or 0 for p in sesion.query(PagoComisionVendedor).filter(PagoComisionVendedor.vendedor_id == vendedor_id).all()), 2)
    pendiente = round(comision_acum - comision_pagada, 2)
    monto = datos.monto if datos.monto is not None else pendiente
    if monto <= 0:
        raise HTTPException(status_code=400, detail="No hay comision pendiente para pagar")
    if monto > pendiente:
        raise HTTPException(status_code=400, detail=f"El monto supera la comision pendiente (${pendiente})")
    pago = PagoComisionVendedor(vendedor_id=vendedor_id, monto=monto)
    sesion.add(pago)
    sesion.commit()
    auditoria.registrar(sesion, "COMISION_VENDEDOR_PAGADA", detalle=f"vendedor={vendedor.usuario} monto={monto}", usuario=admin)
    sesion.commit()
    return {"monto": monto, "pendiente_restante": round(pendiente - monto, 2)}


@router.get("/vendedores/{vendedor_id}/pagos-comision")
def listar_pagos_comision(vendedor_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    pagos = sesion.query(PagoComisionVendedor).filter(PagoComisionVendedor.vendedor_id == vendedor_id).order_by(PagoComisionVendedor.id.desc()).all()
    return [
        {"id": p.id, "monto": p.monto, "creado_en": p.creado_en.isoformat() if p.creado_en else None}
        for p in pagos
    ]

def _vendidas_vendedor_sorteo(sesion: Session, vendedor_id: int, sorteo_id: int) -> int:
    """Cantidad real de jugadas vendidas de un vendedor en un sorteo (fuente de verdad)."""
    return (
        sesion.query(Jugada)
        .filter(
            Jugada.vendedor_id == vendedor_id,
            Jugada.sorteo_id == sorteo_id,
            Jugada.estado.in_(ESTADOS_VENDIDOS),
        )
        .count()
    )


@router.post("/vendedores/{vendedor_id}/sincronizar-cupos")
def sincronizar_cupos_vendedor(vendedor_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    """Recalcula cupo_usado de cada sorteo = jugadas reales vendidas. Sanea cupos desincronizados."""
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    regs = sesion.query(CupoVendedor).filter(CupoVendedor.vendedor_id == vendedor_id).all()
    corregidos = 0
    for r in regs:
        reales = _vendidas_vendedor_sorteo(sesion, vendedor_id, r.sorteo_id)
        if (r.cupo_usado or 0) != reales:
            r.cupo_usado = reales
            corregidos += 1
    sesion.commit()
    auditoria.registrar(sesion, "CUPOS_SYNCRONIZADOS", detalle=f"vendedor={vendedor.usuario} corregidos={corregidos}/{len(regs)}", usuario=admin)
    sesion.commit()
    return {"corregidos": corregidos, "total": len(regs)}

# ---------- JUGADORES (vision global del admin) ----------

@router.get("/revendedores")
def listar_revendedores_admin(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    revs = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.REVENDEDOR).order_by(Usuario.nombre).all()
    salida = []
    for r in revs:
        v = sesion.get(Usuario, r.padre_id) if r.padre_id else None
        salida.append({
            "id": r.id, "usuario": r.usuario, "nombre": r.nombre,
            "vendedor_id": (v.id if v else None), "vendedor": (v.nombre if v else "-"),
        })
    return salida


def _fila_jugador(j: Usuario, sesion: Session, js_count=None, js_sum=None):
    if js_count is None:
        from sqlalchemy import func
        row = (
            sesion.query(func.count(Jugada.id), func.sum(Jugada.precio))
            .filter(Jugada.jugador_id == j.id, Jugada.estado.in_(ESTADOS_VENDIDOS))
            .one()
        )
        js_count, js_sum = row[0] or 0, float(row[1] or 0.0)
    v = sesion.get(Usuario, j.padre_id) if j.padre_id else None
    rev = sesion.get(Usuario, j.revendedor_padre_id) if j.revendedor_padre_id else None
    return {
        "id": j.id, "usuario": j.usuario, "nombre": j.nombre, "telefono": j.telefono,
        "datos_cobro": j.datos_cobro, "cobro_transferencia": bool(j.cobro_transferencia),
        "activo": bool(j.activo),
        "vendedor_id": (v.id if v else None), "vendedor": (v.nombre if v else "-"),
        "vendedor_usuario": (v.usuario if v else "-"),
        "revendedor_id": (rev.id if rev else None), "revendedor": (rev.nombre if rev else None),
        "revendedor_usuario": (rev.usuario if rev else None),
        "via": ("revendedor" if rev else "directo"),
        "jugadas": js_count, "apostado": round(js_sum, 2),
    }


@router.get("/jugadores")
def listar_jugadores_admin(
    q: str | None = None,
    vendedor_id: int | None = None,
    revendedor_id: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = admin_dep,
):
    from sqlalchemy import func, or_
    consulta = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.JUGADOR)
    if q:
        like = f"%{q.strip()}%"
        consulta = consulta.filter(or_(Usuario.usuario.ilike(like), Usuario.nombre.ilike(like), Usuario.telefono.ilike(like)))
    if vendedor_id is not None:
        consulta = consulta.filter(Usuario.padre_id == vendedor_id)
    if revendedor_id is not None:
        consulta = consulta.filter(Usuario.revendedor_padre_id == revendedor_id)
    jugadores = consulta.order_by(Usuario.nombre).all()
    ids = [j.id for j in jugadores]
    mapa = {}
    if ids:
        rows = (
            sesion.query(Jugada.jugador_id, func.count(Jugada.id), func.sum(Jugada.precio))
            .filter(Jugada.jugador_id.in_(ids), Jugada.estado.in_(ESTADOS_VENDIDOS))
            .group_by(Jugada.jugador_id).all()
        )
        mapa = {r[0]: (r[1] or 0, float(r[2] or 0.0)) for r in rows}
    return [_fila_jugador(j, sesion, *(mapa.get(j.id, (0, 0.0)))) for j in jugadores]


@router.put("/jugadores/{jugador_id}")
def editar_jugador_admin(jugador_id: int, datos: JugadorEditarAdmin, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    jugador = sesion.get(Usuario, jugador_id)
    if jugador is None or jugador.rol != RolUsuario.JUGADOR:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")
    if datos.usuario is not None and datos.usuario != jugador.usuario:
        if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario, Usuario.id != jugador_id).first():
            raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
        jugador.usuario = datos.usuario
    if datos.password:
        jugador.password_hash = hash_password(datos.password)
    for campo in ("nombre", "telefono", "datos_cobro", "cobro_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(jugador, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "JUGADOR_EDITADO_ADMIN", detalle=jugador.usuario, usuario=admin)
    sesion.commit()
    return _fila_jugador(jugador, sesion)
