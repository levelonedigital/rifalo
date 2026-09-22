import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_permiso, requerir_rol
from app.core.security import hash_password
from app.modulos_juegos import motor
from app.modulos_juegos.buscador import _actualizar_semanal, costo_a_cubrir
from app.modulos_juegos.modalidades import listar, obtener
from app.modelos.juegos import Aviso, EstadoJugada, EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/admin", tags=["juegos"])

admin_dep = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))

ESTADOS_VENDIDOS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]
NUMEROS_OCULTOS = "••• (numeros ocultos)"
HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validar_hora_cierre(valor):
    if valor is None:
        return None
    if not HORA_RE.match(valor):
        raise HTTPException(status_code=400, detail="Horario de cierre invalido: usa HH:MM (ej: 20:00)")
    return valor


def detalle_por_defecto(modalidad) -> str:
    base = modalidad.resumen_reglas if modalidad else ""
    return base + " Si no se cumplen las condiciones, el sorteo puede pasar a otro horario; se respetan las jugadas."


class SorteoCrear(BaseModel):
    modalidad: str
    horario: str
    fecha: datetime
    hora_cierre: str | None = None
    premio_fijo: float | None = Field(default=None, gt=0)
    pozo_inicial: float | None = Field(default=None, ge=0)
    precio_jugada: float = Field(gt=0)
    pozo_base: float = Field(ge=0)
    casa_pct: float = Field(ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    minimo_cubrir: float | None = Field(default=None, ge=0)
    imagen_url: str | None = None
    detalle: str | None = None


class SorteoEditar(BaseModel):
    horario: str | None = None
    fecha: datetime | None = None
    hora_cierre: str | None = None
    precio_jugada: float | None = Field(default=None, gt=0)
    pozo_base: float | None = Field(default=None, ge=0)
    casa_pct: float | None = Field(default=None, ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    premio_fijo: float | None = Field(default=None, gt=0)
    minimo_cubrir: float | None = Field(default=None, ge=0)
    imagen_url: str | None = None
    detalle: str | None = None


class ResultadoCargar(BaseModel):
    numeros: list[int]


class Reprogramar(BaseModel):
    fecha: datetime


class VendedorCrear(BaseModel):
    usuario: str
    password: str
    nombre: str
    codigo: str = Field(max_length=10)
    comision_pct: float = Field(ge=0, le=100)
    telefono: str | None = None
    datos_transferencia: str | None = None


class VendedorEditar(BaseModel):
    nombre: str | None = None
    telefono: str | None = None
    codigo: str | None = Field(default=None, max_length=10)
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    datos_transferencia: str | None = None
    password: str | None = None
    activo: bool | None = None


class PozoVacanteCrear(BaseModel):
    fecha: datetime


# ---------- MODALIDADES ----------

@router.get("/modalidades")
def listar_modalidades():
    return listar()


# ---------- SORTEOS ----------

@router.post("/sorteos")
def crear_sorteo(datos: SorteoCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    """Crea el sorteo en PREPARACION (inactivo). El admin lo revisa/edita y luego lo activa."""
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
    hora_cierre = validar_hora_cierre(datos.hora_cierre)
    pozo = datos.pozo_inicial if datos.pozo_inicial is not None else datos.pozo_base
    sorteo = Sorteo(
        modalidad=datos.modalidad,
        horario=datos.horario,
        fecha=datos.fecha,
        hora_cierre=hora_cierre,
        estado=EstadoSorteo.PREPARACION,
        premio_fijo=datos.premio_fijo,
        pozo_inicial=pozo,
        precio_jugada=datos.precio_jugada,
        pozo_base=datos.pozo_base,
        casa_pct=datos.casa_pct,
        vendedor_pct=datos.vendedor_pct,
        minimo_cubrir=datos.minimo_cubrir,
        imagen_url=datos.imagen_url,
        detalle=datos.detalle or detalle_por_defecto(modalidad),
    )
    sesion.add(sorteo)
    sesion.commit()
    sesion.refresh(sorteo)
    auditoria.registrar(sesion, "SORTEO_CREADO", detalle=f"{sorteo.modalidad} {sorteo.horario} id={sorteo.id} pozo={pozo} (en preparacion)", usuario=admin)
    sesion.commit()
    return {"id": sorteo.id, "modalidad": sorteo.modalidad, "horario": sorteo.horario, "pozo_inicial": pozo}


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
                "solo_participantes": s.solo_participantes,
                "busqueda_agotada": s.busqueda_agotada,
                "precio_jugada": s.precio_jugada,
                "pozo_base": s.pozo_base,
                "casa_pct": s.casa_pct,
                "vendedor_pct": s.vendedor_pct,
                "minimo_cubrir": s.minimo_cubrir,
                "imagen_url": s.imagen_url,
                "detalle": s.detalle,
                "costo": costo,
                "costo_cubierto": (s.recaudado or 0.0) >= costo,
            }
        )
    return salida


@router.get("/sorteos/{sorteo_id}/resumen")
def resumen_sorteo(sorteo_id: int, sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    """Resumen completo de un unico sorteo: vendido, reparto y premios."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    jugadas = sesion.query(Jugada).filter(Jugada.sorteo_id == sorteo.id).all()
    vendidas = [j for j in jugadas if j.estado in ESTADOS_VENDIDOS]
    ganadoras = [j for j in jugadas if j.estado == EstadoJugada.GANADORA]
    return {
        "sorteo_id": sorteo.id,
        "modalidad": sorteo.modalidad,
        "horario": sorteo.horario,
        "fecha": sorteo.fecha.isoformat(),
        "estado": sorteo.estado.value,
        "resultados": sorteo.resultados,
        "pozo": sorteo.pozo_actual,
        "recaudado": sorteo.recaudado or 0.0,
        "costo": costo_a_cubrir(sorteo),
        "costo_cubierto": (sorteo.recaudado or 0.0) >= costo_a_cubrir(sorteo),
        "jugadas_cargadas": len(jugadas),
        "jugadas_vendidas": len(vendidas),
        "vendido": round(sum(j.precio for j in vendidas), 2),
        "casa": round(sum(j.monto_casa or 0 for j in vendidas), 2),
        "vendedores": round(sum(j.monto_vendedor or 0 for j in vendidas), 2),
        "revendedores": round(sum(j.monto_revendedor or 0 for j in vendidas), 2),
        "pozo_aportado": round(sum(j.monto_pozo or 0 for j in vendidas), 2),
        "premios_pagados": round(sum(j.premio or 0 for j in ganadoras), 2),
        "ganadoras": [j.id for j in ganadoras],
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
    """Cancela la hora del sorteo. Jugadas y pozo siguen en juego, esperando nuevo horario."""
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
    """Fija el nuevo horario de un sorteo reprogramando. Jugadas y pozo quedan intactos."""
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado != EstadoSorteo.REPROGRAMANDO:
        raise HTTPException(status_code=400, detail="El sorteo no esta en estado reprogramando")
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    sorteo.fecha = datos.fecha
    sorteo.estado = EstadoSorteo.PROGRAMADO
    sorteo.aviso_costo_enviado = False
    aviso = Aviso(
        texto=(
            f"Sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario}) reprogramado: "
            f"nuevo dia {datos.fecha.strftime('%d/%m/%Y')}."
        ),
        destino="todos",
    )
    sesion.add(aviso)
    sesion.commit()
    auditoria.registrar(sesion, "SORTEO_REPROGRAMADO", detalle=f"sorteo={sorteo.id} nueva_fecha={datos.fecha.isoformat()}", usuario=admin)
    sesion.commit()
    return {"ok": True, "estado": sorteo.estado.value, "fecha": sorteo.fecha.isoformat()}


@router.post("/sorteos/{sorteo_id}/resultado")
def cargar_resultado(sorteo_id: int, datos: ResultadoCargar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("cargar_resultados"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="El sorteo ya esta liquidado")
    if sorteo.estado == EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="Primero cerrá el sorteo")
    if sorteo.modalidad == "semanal":
        raise HTTPException(status_code=400, detail="El semanal se liquida solo con los sorteos diarios")
    if len(datos.numeros) != 20 or len(set(datos.numeros)) != 20 or any(n < 0 or n > 99 for n in datos.numeros):
        raise HTTPException(status_code=400, detail="Deben ser 20 numeros distintos entre 0 y 99")
    sorteo.resultados = ",".join(f"{n:02d}" for n in datos.numeros)
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


# ---------- JUGADAS (numeros ocultos para todos) ----------

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
    """Ficha individual de una jugada. Los numeros quedan ocultos por privacidad."""
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
        "creada_en": j.creada_en.isoformat() if j.creada_en else None,
    }


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
        {
            "id": v.id,
            "usuario": v.usuario,
            "nombre": v.nombre,
            "codigo": v.codigo,
            "comision_pct": v.comision_pct,
            "telefono": v.telefono,
            "datos_transferencia": v.datos_transferencia,
            "activo": v.activo,
        }
        for v in vendedores
    ]


@router.put("/vendedores/{vendedor_id}")
def editar_vendedor(vendedor_id: int, datos: VendedorEditar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    """Edicion completa del vendedor con las mismas opciones que al crearlo."""
    vendedor = sesion.get(Usuario, vendedor_id)
    if vendedor is None or vendedor.rol != RolUsuario.VENDEDOR:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    if datos.codigo is not None:
        codigo = datos.codigo.upper()
        otro = sesion.query(Usuario).filter(Usuario.codigo == codigo, Usuario.id != vendedor_id).first()
        if otro:
            raise HTTPException(status_code=400, detail="El codigo ya existe")
        vendedor.codigo = codigo
    if datos.password:
        vendedor.password_hash = hash_password(datos.password)
    for campo in ("nombre", "telefono", "comision_pct", "datos_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(vendedor, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "VENDEDOR_EDITADO", detalle=vendedor.usuario, usuario=admin)
    sesion.commit()
    return {
        "id": vendedor.id,
        "usuario": vendedor.usuario,
        "codigo": vendedor.codigo,
        "comision_pct": vendedor.comision_pct,
        "activo": vendedor.activo,
    }


# ---------- RESUMEN GENERAL ----------

@router.get("/resumen-general")
def resumen_general(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    """Cuenta todas las jugadas que llegaron a aprobadas (incluidas ya liquidadas)."""
    jugadas = sesion.query(Jugada).filter(Jugada.estado.in_(ESTADOS_VENDIDOS)).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "casa": round(sum(j.monto_casa or 0 for j in jugadas), 2),
        "vendedores": round(sum(j.monto_vendedor or 0 for j in jugadas), 2),
        "revendedores": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
        "premios_pagados": round(sum(j.premio or 0 for j in jugadas if j.estado == EstadoJugada.GANADORA), 2),
    }
