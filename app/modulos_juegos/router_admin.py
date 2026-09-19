from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.database import obtener_sesion
from app.core.dependencias import requerir_permiso, requerir_rol
from app.core.security import hash_password
from app.modulos_juegos import motor
from app.modulos_juegos.buscador import _actualizar_semanal
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, ModuloJuego, ReglasSistema, Sorteo
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/admin", tags=["juegos"])

admin_dep = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN))


class SorteoCrear(BaseModel):
    modulo: ModuloJuego
    horario: str
    fecha: datetime
    premio_fijo: float | None = Field(default=None, gt=0)
    pozo_inicial: float | None = Field(default=None, ge=0)


class ResultadoCargar(BaseModel):
    numeros: list[int]


class ReglasEditar(BaseModel):
    precio_clasico: float | None = None
    precio_semanal: float | None = None
    precio_rifa: float | None = None
    pozo_base_clasico: float | None = None
    pozo_base_semanal: float | None = None
    pozo_pct: float | None = Field(default=None, ge=0, le=100)
    vendedor_pct: float | None = Field(default=None, ge=0, le=100)
    horarios: str | None = None
    semanal_horario: str | None = None
    semanal_dia_inicio: int | None = Field(default=None, ge=0, le=6)
    semanal_dia_fin: int | None = Field(default=None, ge=0, le=6)
    busqueda_inicio_min: int | None = None
    busqueda_intervalo_min: int | None = None
    busqueda_duracion_min: int | None = None


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
    comision_pct: float | None = Field(default=None, ge=0, le=100)
    datos_transferencia: str | None = None
    activo: bool | None = None


class PozoVacanteCrear(BaseModel):
    fecha: datetime


# ---------- REGLAS ----------

@router.get("/reglas")
def ver_reglas(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    reglas = motor.obtener_reglas(sesion)
    return {
        "precio_clasico": reglas.precio_clasico,
        "precio_semanal": reglas.precio_semanal,
        "precio_rifa": reglas.precio_rifa,
        "pozo_base_clasico": reglas.pozo_base_clasico,
        "pozo_base_semanal": reglas.pozo_base_semanal,
        "pozo_pct": reglas.pozo_pct,
        "vendedor_pct": reglas.vendedor_pct,
        "horarios": reglas.dict_horarios(),
        "semanal_horario": reglas.semanal_horario,
        "semanal_dia_inicio": reglas.semanal_dia_inicio,
        "semanal_dia_fin": reglas.semanal_dia_fin,
        "busqueda_inicio_min": reglas.busqueda_inicio_min,
        "busqueda_intervalo_min": reglas.busqueda_intervalo_min,
        "busqueda_duracion_min": reglas.busqueda_duracion_min,
    }


@router.put("/reglas")
def editar_reglas(datos: ReglasEditar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL))):
    reglas = motor.obtener_reglas(sesion)
    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(reglas, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "REGLAS_EDITADAS", detalle=str(datos.model_dump(exclude_none=True)), usuario=admin)
    sesion.commit()
    return {"ok": True}


# ---------- SORTEOS ----------

@router.post("/sorteos")
def crear_sorteo(datos: SorteoCrear, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    reglas = motor.obtener_reglas(sesion)
    if datos.horario not in reglas.dict_horarios():
        raise HTTPException(status_code=400, detail="Horario inexistente en las reglas")
    if datos.pozo_inicial is not None:
        pozo = datos.pozo_inicial
    elif datos.modulo == ModuloJuego.CLASICO:
        pozo = reglas.pozo_base_clasico
    elif datos.modulo == ModuloJuego.SEMANAL:
        pozo = reglas.pozo_base_semanal
    else:
        pozo = 0.0
    sorteo = Sorteo(
        modulo=datos.modulo,
        horario=datos.horario,
        fecha=datos.fecha,
        premio_fijo=datos.premio_fijo,
        pozo_inicial=pozo,
    )
    sesion.add(sorteo)
    sesion.commit()
    sesion.refresh(sorteo)
    auditoria.registrar(sesion, "SORTEO_CREADO", detalle=f"{sorteo.modulo.value} {sorteo.horario} id={sorteo.id} pozo={pozo}", usuario=admin)
    sesion.commit()
    return {"id": sorteo.id, "modulo": sorteo.modulo.value, "horario": sorteo.horario, "pozo_inicial": pozo}


@router.get("/sorteos")
def listar_sorteos(sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("configurar_sorteos"))):
    sorteos = sesion.query(Sorteo).order_by(Sorteo.id.desc()).limit(100).all()
    return [
        {
            "id": s.id,
            "modulo": s.modulo.value,
            "horario": s.horario,
            "fecha": s.fecha.isoformat(),
            "estado": s.estado.value,
            "resultados": s.resultados,
            "pozo": s.pozo_actual,
            "recaudado": s.recaudado,
            "solo_participantes": s.solo_participantes,
            "busqueda_agotada": s.busqueda_agotada,
        }
        for s in sorteos
    ]


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


@router.post("/sorteos/{sorteo_id}/resultado")
def cargar_resultado(sorteo_id: int, datos: ResultadoCargar, sesion: Session = Depends(obtener_sesion), admin: Usuario = Depends(requerir_permiso("cargar_resultados"))):
    sorteo = sesion.get(Sorteo, sorteo_id)
    if sorteo is None:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    if sorteo.estado == EstadoSorteo.LIQUIDADO:
        raise HTTPException(status_code=400, detail="El sorteo ya esta liquidado")
    if sorteo.estado == EstadoSorteo.PROGRAMADO:
        raise HTTPException(status_code=400, detail="Primero cerrá el sorteo")
    if sorteo.modulo == ModuloJuego.SEMANAL:
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
    if sorteo.estado != EstadoSorteo.LIQUIDADO or sorteo.modulo == ModuloJuego.RIFA:
        raise HTTPException(status_code=400, detail="Solo sorteos liquidados de clasico o semanal")
    ganadoras = sesion.query(Jugada).filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.GANADORA).count()
    if ganadoras > 0:
        raise HTTPException(status_code=400, detail="Este sorteo ya tuvo ganadores")
    if datos.fecha.weekday() == 6:
        raise HTTPException(status_code=400, detail="Los domingos no hay sorteos")
    nuevo = motor.crear_pozo_vacante(sesion, sorteo, datos.fecha, motor.obtener_reglas(sesion))
    sesion.commit()
    sesion.refresh(nuevo)
    auditoria.registrar(sesion, "POZO_VACANTE_CREADO", detalle=f"origen={sorteo.id} nuevo={nuevo.id}", usuario=admin)
    sesion.commit()
    return {"id": nuevo.id, "pozo_inicial": nuevo.pozo_inicial, "participantes": nuevo.participantes}


# ---------- VISTA GENERAL DE JUGADAS ----------

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
                "numeros": j.numeros,
                "precio": j.precio,
                "estado": j.estado.value,
                "premio": j.premio,
                "jugador_nombre": j.jugador_nombre,
            }
        )
    return salida


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
    for campo in ("nombre", "telefono", "comision_pct", "datos_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(vendedor, campo, valor)
    sesion.commit()
    auditoria.registrar(sesion, "VENDEDOR_EDITADO", detalle=vendedor.usuario, usuario=admin)
    sesion.commit()
    return {"id": vendedor.id, "usuario": vendedor.usuario, "comision_pct": vendedor.comision_pct, "activo": vendedor.activo}


# ---------- RESUMEN GENERAL ----------

@router.get("/resumen-general")
def resumen_general(sesion: Session = Depends(obtener_sesion), admin: Usuario = admin_dep):
    jugadas = sesion.query(Jugada).filter(Jugada.estado == EstadoJugada.APROBADA).all()
    return {
        "jugadas_aprobadas": len(jugadas),
        "vendido": round(sum(j.precio for j in jugadas), 2),
        "casa": round(sum(j.monto_casa or 0 for j in jugadas), 2),
        "vendedores": round(sum(j.monto_vendedor or 0 for j in jugadas), 2),
        "revendedores": round(sum(j.monto_revendedor or 0 for j in jugadas), 2),
        "premios_pagados": round(sum(j.premio or 0 for j in jugadas if j.estado == EstadoJugada.GANADORA), 2),
    }
